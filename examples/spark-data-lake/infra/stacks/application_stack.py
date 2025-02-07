# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from aws_cdk import Stack, RemovalPolicy, Names
from aws_cdk import aws_iam as iam
from constructs import Construct
import cdklabs.aws_data_solutions_framework as dsf

from stacks.demo_helpers.data_load import DataLoad
from stacks.demo_helpers.spark_job_trigger import SparkJobTrigger


class SparkApplicationStackFactory(dsf.utils.ApplicationStackFactory):
    """Implements ApplicationStackFactory from DSF on AWS to create a self-mutable CICD pipeline for Spark app.
    See Spark CICD docs for more details."""

    def create_stack(self, scope: Construct, stage: dsf.utils.CICDStage) -> Stack:
        return ApplicationStack(scope, "EmrApplicationStack", stage)


class ApplicationStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, stage: dsf.utils.CICDStage=None, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Use DSF on AWS to create a data lake storage and Glue data catalog database for the example data.
        storage = dsf.storage.DataLakeStorage(
            self, "DataLakeStorage", removal_policy=RemovalPolicy.DESTROY
        )

        catalog = dsf.governance.DataLakeCatalog(
            self, "DataLakeCatalog",
            data_lake_storage=storage,
            database_name='spark_data_lake',
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Helper to load example data to bronze bucket. For the demo purposes only.
        DataLoad(
            self,
            "DataLoad",
            src_bucket_name="nyc-tlc",
            src_bucket_prefix="trip data/",
            storage=storage,
        )

        processing_exec_role = dsf.processing.SparkEmrServerlessRuntime.create_execution_role(self, "ProcessingExecRole")

        storage.gold_bucket.grant_read_write(processing_exec_role)
        storage.silver_bucket.grant_read(processing_exec_role)

        # Use DSF on AWS to create Spark EMR serverless runtime, package Spark app, and create a Spark job.
        spark_runtime = dsf.processing.SparkEmrServerlessRuntime(
            self, "SparkProcessingRuntime", name="TaxiAggregation",
            removal_policy=RemovalPolicy.DESTROY,
        )
        spark_app = dsf.processing.PySparkApplicationPackage(
            self,
            "PySparkApplicationPackage",
            entrypoint_path="./../spark/src/agg_trip_distance.py",
            application_name="taxi-trip-aggregation",
            removal_policy=RemovalPolicy.DESTROY,
        )

        spark_app.artifacts_bucket.grant_read_write(processing_exec_role)

        params = (
            f"--conf"
            f" spark.emr-serverless.driverEnv.SOURCE_LOCATION=s3://{storage.silver_bucket.bucket_name}/spark_data_lake/nyc-taxi"
            f" --conf spark.emr-serverless.driverEnv.TARGET_LOCATION=s3://{storage.gold_bucket.bucket_name}/spark_data_lake"
        )

        spark_job = dsf.processing.SparkEmrServerlessJob(
            self,
            "SparkProcessingJob",
            dsf.processing.SparkEmrServerlessJobProps(
                name=f"taxi-agg-job-{Names.unique_resource_name(self)}",
                application_id=spark_runtime.application.attr_application_id,
                execution_role=processing_exec_role,
                spark_submit_entry_point=spark_app.entrypoint_uri,
                spark_submit_parameters=params,
                removal_policy=RemovalPolicy.DESTROY,
            )
        )

        # Helper with the custom resource to trigger the Spark job. For the demo purposes only.
        SparkJobTrigger(self, "JobTrigger", spark_job=spark_job, db=catalog.gold_catalog_database)

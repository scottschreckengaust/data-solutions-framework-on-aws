// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/* eslint-disable */
import { SecretsManagerClient, GetSecretValueCommand } from '@aws-sdk/client-secrets-manager';
/* eslint-enable */
import { sendRequest } from './helper.mjs';

const region = process.env.REGION;
const client = new SecretsManagerClient({ region });

/*type Event = {
  RequestType: string;
  ResourceProperties: { path: string; body: string };
};*/
//export async function handler(event: Event): Promise<any> {
export async function handler(event) {
  console.log(JSON.stringify(event, null, 1));
  switch (event.RequestType) {
    case 'Create':
    case 'Update':
      await onUpdate(event);
      break;
    case 'Delete':
      await onDelete(event);
      break;
    default:
      throw new Error(`invalid request type: ${event.RequestType}`);
  }
}

const onUpdate = async (event) => {
  const { path, body } = event.ResourceProperties;
  const secretsResolvedBody = await resolveSecrets(body);
  await sendRequest({
    method: 'PUT',
    path,
    body: secretsResolvedBody,
  });
};

const onDelete = async (event) => {
  const { path } = event.ResourceProperties;
  await sendRequest({
    method: 'DELETE',
    path,
  });
};

const resolveSecrets = async (object) => {
  if (typeof object !== 'object' || object === null) return object;
  if (Array.isArray(object)) {
    return Promise.all(object.map(resolveSecrets));
  }
  const resolvedObject = {};
  for (let key in object) {
    if (Object.prototype.hasOwnProperty.call(object, key)) {
      let value = object[key];
      if (typeof value !== 'object' && value !== null && key.endsWith('FieldSecretArn')) {
        const secretFieldName = key.replace('FieldSecretArn', '');
        const secret = await client.send(new GetSecretValueCommand({ SecretId: value }));
        value = JSON.parse(secret.SecretString)[secretFieldName];
        key = secretFieldName;
      }
      resolvedObject[key] = await resolveSecrets(value);
    }
  }
  return resolvedObject;
};
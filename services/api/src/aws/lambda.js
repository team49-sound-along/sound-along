import serverlessExpress from "@codegenie/serverless-express";
import { createAwsApp, createAwsClients } from "./awsApp.js";

export function createHandler(env, clients) {
  return serverlessExpress({ app: createAwsApp(env, clients) });
}

// Built once per container, reused across invocations.
export const handler = createHandler(process.env, createAwsClients());

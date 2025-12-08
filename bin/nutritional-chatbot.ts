#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import 'source-map-support/register';
import { NutritionalChatbotStack } from '../lib/nutritional-chatbot-stack';

const app = new cdk.App();
new NutritionalChatbotStack(app, 'NutritionalChatbotStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: 'us-east-1'
  },
});

app.synth();

import * as cdk from 'aws-cdk-lib/core';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as path from 'path';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';


// import * as sqs from 'aws-cdk-lib/aws-sqs';

export class NutritionalChatbotStack extends cdk.Stack {
  public readonly apiUrl: string;
  
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // The code that defines your stack goes here
    const secrets = secretsmanager.Secret.fromSecretNameV2(
      this,
      'ChatbotSecrets',
      `kidney-nutritional-chatbot/secrets`
    );

    // Lambda Dependency Layer
    const dependenciesLayer = new lambda.LayerVersion(this, 'DependenciesLayer', {
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/chatbot'), {
        bundling: {
          image: lambda.Runtime.PYTHON_3_11.bundlingImage,
          command: [
            'bash', '-c',
            'pip install -r requirements.txt -t /asset-output/python && cp -r . /asset-output/'
          ],
        },
      }),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_11],
      description: 'A layer with all dependencies for the Nutritional Chatbot Lambdas',
    });
    
    // LAMBDA FUNCTION
    const chatbotFunction = new lambda.Function(this, 'NutritionalChatbotFunction', {
      functionName: 'kidney-nutritional-chatbot-function',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/chatbot')),
      layers: [dependenciesLayer],
      timeout: cdk.Duration.seconds(900),
      memorySize: 2048,
      environment: {
        OPENAI_API_KEY: secrets.secretValueFromJson('OPENAI_API_KEY').unsafeUnwrap(),
        SUPABASE_URL: secrets.secretValueFromJson('SUPABASE_URL').unsafeUnwrap(),
        SUPABASE_SERVICE_KEY: secrets.secretValueFromJson('SUPABASE_SERVICE_KEY').unsafeUnwrap(),
      },
      description: 'Lambda function for the Nutritional Chatbot using OpenAI and Supabase',
    });


    // Grant secrets access
    secrets.grantRead(chatbotFunction);

    // API Gateway to expose the Lambda function
    const api = new apigateway.RestApi(this, 'NutritionalChatbotApi', {
      restApiName: 'Kidney Nutritional Chatbot Service',
      description: 'This service serves the Kidney Nutritional Chatbot.',
      deployOptions: {
        throttlingBurstLimit: 100,
        throttlingRateLimit: 50,
        dataTraceEnabled: true,
        metricsEnabled: true,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: ['POST', 'OPTIONS'],
        allowHeaders: [
          'Content-Type',
          'Authorization',
          'X-Session-Id',
        ],
        maxAge: cdk.Duration.days(1),
      }
    });

    // /chat endpoint
    const chatResource = api.root.addResource('chat');

    const chatIntegration = new apigateway.LambdaIntegration(chatbotFunction, {
      timeout: cdk.Duration.seconds(29),
      proxy: true
    });

    chatResource.addMethod('POST', chatIntegration, {
      apiKeyRequired: false,
      methodResponses: [
        {
          statusCode: '200',
          responseParameters:{
            'method.response.header.Access-Control-Allow-Origin': true,
          },
        },
        { statusCode: '400' },
        { statusCode: '500' },
      ],
    });

    // Health check endpoint
    const healthResource = api.root.addResource('health');
    healthResource.addMethod('GET', new apigateway.LambdaIntegration(
      new lambda.Function(this, 'HealthCheckFunction', {
        runtime: lambda.Runtime.PYTHON_3_11,
        handler: 'index.handler',
        code: lambda.Code.fromInline(`
        def handler(event, context):
            return {
                'statusCode': 200,
                'body': '{"status": "healthy"}'
            }
        `),
        timeout: cdk.Duration.seconds(5),
      })
    ));

    // ==== OUTPUTS ====
    this.apiUrl = api.url;

    new cdk.CfnOutput(this, 'NutritionalChatbotApiUrl', {
      value: this.apiUrl,
      description: 'The URL of the Nutritional Chatbot API Gateway',
      exportName: `kidney-nutritional-chatbot-api-url`,
    });

    new cdk.CfnOutput(this, 'ChatEndpoint', {
      value: `${api.url}chat`,
      description: 'Chat endpoint URL',
    });

     new cdk.CfnOutput(this, 'FunctionName', {
      value: chatbotFunction.functionName,
      description: 'Lambda function name',
    });


    
    // example resource
    // const queue = new sqs.Queue(this, 'NutritionalChatbotQueue', {
    //   visibilityTimeout: cdk.Duration.seconds(300)
    // });
  }
}

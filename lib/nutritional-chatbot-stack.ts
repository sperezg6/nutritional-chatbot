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
            'pip install -r requirements.txt -t /asset-output/python && cp -r . /asset-output/ && chmod +x /asset-output/run_streaming.sh'
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

    // ===== LAMBDA FUNCTION URL (bypasses API Gateway 29s limit) =====
    const chatFunctionUrl = chatbotFunction.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ['*'],
        allowedMethods: [lambda.HttpMethod.POST, lambda.HttpMethod.OPTIONS],
        allowedHeaders: ['Content-Type', 'Authorization', 'X-Session-Id'],
      },
    });

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

    // ===== STREAMING LAMBDA FUNCTION =====

    // Lambda Web Adapter Layer (for Python streaming support)
    const lambdaAdapterLayer = lambda.LayerVersion.fromLayerVersionArn(
      this,
      'LambdaAdapterLayer',
      `arn:aws:lambda:${this.region}:753240598075:layer:LambdaAdapterLayerX86:25`
    );

    // Streaming Lambda Function with FastAPI + Lambda Web Adapter
    const streamingChatbotFunction = new lambda.Function(this, 'StreamingChatbotFunction', {
      functionName: 'kidney-nutritional-chatbot-streaming-function',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'run_streaming.sh',  // Points to startup script
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/chatbot')),
      layers: [dependenciesLayer, lambdaAdapterLayer],
      timeout: cdk.Duration.minutes(15),  // Extended timeout for streaming
      memorySize: 2048,
      environment: {
        OPENAI_API_KEY: secrets.secretValueFromJson('OPENAI_API_KEY').unsafeUnwrap(),
        SUPABASE_URL: secrets.secretValueFromJson('SUPABASE_URL').unsafeUnwrap(),
        SUPABASE_SERVICE_KEY: secrets.secretValueFromJson('SUPABASE_SERVICE_KEY').unsafeUnwrap(),
        AWS_LAMBDA_EXEC_WRAPPER: '/opt/bootstrap',  // Required for Lambda Web Adapter
        AWS_LWA_INVOKE_MODE: 'response_stream',  // Enable streaming mode
        AWS_LWA_PORT: '8080',  // FastAPI port
        PYTHONPATH: '/var/task:/opt/python',  // Ensure Python can find layer modules
      },
      description: 'Streaming Lambda function for Nutritional Chatbot using OpenAI Agents and FastAPI',
    });

    // Grant secrets access to streaming function
    secrets.grantRead(streamingChatbotFunction);

    // ===== STREAMING FUNCTION URL (true streaming, no API Gateway buffering) =====
    // Note: RESPONSE_STREAM invoke mode enables true SSE streaming
    const streamingFunctionUrl = new lambda.FunctionUrl(this, 'StreamingFunctionUrl', {
      function: streamingChatbotFunction,
      authType: lambda.FunctionUrlAuthType.NONE,
      invokeMode: lambda.InvokeMode.RESPONSE_STREAM,
      cors: {
        allowedOrigins: ['*'],
        allowedMethods: [lambda.HttpMethod.POST, lambda.HttpMethod.OPTIONS],
        allowedHeaders: ['Content-Type', 'Authorization', 'X-Session-Id'],
      },
    });

    // /chat-stream endpoint with streaming configuration
    const chatStreamResource = api.root.addResource('chat-stream');

    const streamingIntegration = new apigateway.LambdaIntegration(streamingChatbotFunction, {
      proxy: true,
      // Enable streaming response mode
      integrationResponses: [{
        statusCode: '200',
        responseParameters: {
          'method.response.header.Access-Control-Allow-Origin': "'*'",
          'method.response.header.Cache-Control': "'no-cache'",
          'method.response.header.Connection': "'keep-alive'",
          'method.response.header.Content-Type': "'text/event-stream'",
          'method.response.header.X-Accel-Buffering': "'no'",
        },
      }],
    });

    chatStreamResource.addMethod('POST', streamingIntegration, {
      apiKeyRequired: false,
      methodResponses: [
        {
          statusCode: '200',
          responseParameters: {
            'method.response.header.Access-Control-Allow-Origin': true,
            'method.response.header.Cache-Control': true,
            'method.response.header.Connection': true,
            'method.response.header.Content-Type': true,
            'method.response.header.X-Accel-Buffering': true,
          },
        },
        { statusCode: '400' },
        { statusCode: '500' },
      ],
      requestParameters: {
        'method.request.header.Content-Type': true,
      },
    });

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

    new cdk.CfnOutput(this, 'ChatStreamEndpoint', {
      value: `${api.url}chat-stream`,
      description: 'Streaming chat endpoint URL',
    });

     new cdk.CfnOutput(this, 'FunctionName', {
      value: chatbotFunction.functionName,
      description: 'Lambda function name',
    });

    new cdk.CfnOutput(this, 'StreamingFunctionName', {
      value: streamingChatbotFunction.functionName,
      description: 'Streaming Lambda function name',
    });

    // ===== FUNCTION URL OUTPUTS (use these instead of API Gateway for long requests) =====
    new cdk.CfnOutput(this, 'ChatFunctionUrl', {
      value: chatFunctionUrl.url,
      description: 'Lambda Function URL for chat (no 29s timeout limit, uses Lambda 15min timeout)',
    });

    new cdk.CfnOutput(this, 'StreamingFunctionUrl', {
      value: streamingFunctionUrl.url,
      description: 'Lambda Function URL for streaming chat (true SSE streaming)',
    });


    
    // example resource
    // const queue = new sqs.Queue(this, 'NutritionalChatbotQueue', {
    //   visibilityTimeout: cdk.Duration.seconds(300)
    // });
  }
}

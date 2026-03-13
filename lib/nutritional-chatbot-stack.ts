import * as cdk from 'aws-cdk-lib/core';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as path from 'path';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { AttributeType } from 'aws-cdk-lib/aws-dynamodb';
import { PolicyStatement } from 'aws-cdk-lib/aws-iam';
import { DynamoDBConstruct } from './constructs/dynamoDb/dynamoDB-construct';
import { LambdaConstruct } from './constructs/lambda/lambda-construct';

export class NutritionalChatbotStack extends cdk.Stack {
  public readonly apiUrl: string;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ===== SECRETS =====
    const secrets = secretsmanager.Secret.fromSecretNameV2(
      this,
      'ChatbotSecrets',
      `kidney-nutritional-chatbot/secrets`
    );

    // ===== DYNAMODB TABLES =====

    const sessionsTable = new DynamoDBConstruct(this, 'SessionsTable', {
      tableName: 'nutritional-chatbot-sessions',
      partitionKey: 'session_id',
    });

    const messagesTable = new DynamoDBConstruct(this, 'MessagesTable', {
      tableName: 'nutritional-chatbot-messages',
      partitionKey: 'session_id',
      sortKey: 'sequence_number',
      sortKeyType: AttributeType.NUMBER,
      globalSecondaryIndexes: [
        {
          indexName: 'by_message_id',
          partitionKey: 'message_id',
        },
      ],
    });

    const analyticsTable = new DynamoDBConstruct(this, 'AnalyticsTable', {
      tableName: 'nutritional-chatbot-analytics',
      partitionKey: 'session_id',
      sortKey: 'created_at',
      globalSecondaryIndexes: [
        {
          indexName: 'by_date',
          partitionKey: 'date_partition',
          sortKey: 'created_at',
        },
      ],
    });

    const feedbackTable = new DynamoDBConstruct(this, 'FeedbackTable', {
      tableName: 'nutritional-chatbot-feedback',
      partitionKey: 'session_id',
      sortKey: 'created_at',
      globalSecondaryIndexes: [
        {
          indexName: 'by_date',
          partitionKey: 'date_partition',
          sortKey: 'created_at',
        },
      ],
    });

    // Collect all table ARNs + GSI ARNs for IAM
    const allTableArns = [
      sessionsTable.table.tableArn,
      messagesTable.table.tableArn,
      analyticsTable.table.tableArn,
      feedbackTable.table.tableArn,
    ];
    const allArns = [
      ...allTableArns,
      ...allTableArns.map(arn => `${arn}/index/*`),
    ];

    const dynamoDbPolicy = new PolicyStatement({
      actions: [
        'dynamodb:GetItem',
        'dynamodb:PutItem',
        'dynamodb:UpdateItem',
        'dynamodb:DeleteItem',
        'dynamodb:Query',
        'dynamodb:Scan',
      ],
      resources: allArns,
    });

    // Common environment variables
    const tableEnvVars = {
      SESSIONS_TABLE: sessionsTable.tableName,
      MESSAGES_TABLE: messagesTable.tableName,
      ANALYTICS_TABLE: analyticsTable.tableName,
      FEEDBACK_TABLE: feedbackTable.tableName,
    };

    // ===== LAMBDA DEPENDENCY LAYER =====
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

    // ===== CHATBOT LAMBDA =====
    const chatbotLambda = new LambdaConstruct(this, 'ChatbotFunction', {
      functionName: 'kidney-nutritional-chatbot-function',
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/chatbot')),
      layers: [dependenciesLayer],
      timeout: cdk.Duration.seconds(900),
      memorySize: 2048,
      environment: {
        OPENAI_API_KEY: secrets.secretValueFromJson('OPENAI_API_KEY').unsafeUnwrap(),
        ...tableEnvVars,
      },
      additionalPolicies: [dynamoDbPolicy],
      description: 'Lambda function for the Nutritional Chatbot using OpenAI and DynamoDB',
    });

    // Grant secrets access
    secrets.grantRead(chatbotLambda.lambdaFunction);

    // ===== API GATEWAY =====
    const api = new apigateway.RestApi(this, 'NutritionalChatbotApi', {
      restApiName: 'Kidney Nutritional Chatbot Service',
      description: 'This service serves the Kidney Nutritional Chatbot.',
      deployOptions: {
        throttlingBurstLimit: 100,
        throttlingRateLimit: 50,
        dataTraceEnabled: false,
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
    const chatIntegration = new apigateway.LambdaIntegration(chatbotLambda.lambdaFunction, {
      timeout: cdk.Duration.seconds(29),
      proxy: true
    });

    chatResource.addMethod('POST', chatIntegration, {
      apiKeyRequired: false,
      methodResponses: [
        {
          statusCode: '200',
          responseParameters: {
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

    // ===== STREAMING LAMBDA =====

    const lambdaAdapterLayer = lambda.LayerVersion.fromLayerVersionArn(
      this,
      'LambdaAdapterLayer',
      `arn:aws:lambda:${this.region}:753240598075:layer:LambdaAdapterLayerX86:25`
    );

    const streamingLambda = new LambdaConstruct(this, 'StreamingChatbotFunction', {
      functionName: 'kidney-nutritional-chatbot-streaming-function',
      handler: 'run_streaming.sh',
      code: lambda.Code.fromAsset(path.join(__dirname, '../lambda/chatbot')),
      layers: [dependenciesLayer, lambdaAdapterLayer],
      timeout: cdk.Duration.minutes(15),
      memorySize: 2048,
      environment: {
        OPENAI_API_KEY: secrets.secretValueFromJson('OPENAI_API_KEY').unsafeUnwrap(),
        AWS_LAMBDA_EXEC_WRAPPER: '/opt/bootstrap',
        AWS_LWA_INVOKE_MODE: 'response_stream',
        AWS_LWA_PORT: '8080',
        PYTHONPATH: '/var/task:/opt/python',
        ...tableEnvVars,
      },
      additionalPolicies: [dynamoDbPolicy],
      description: 'Streaming Lambda function for Nutritional Chatbot using OpenAI Agents and FastAPI',
    });

    // Grant secrets access to streaming function
    secrets.grantRead(streamingLambda.lambdaFunction);

    // /chat-stream endpoint
    const chatStreamResource = api.root.addResource('chat-stream');

    const streamingIntegration = new apigateway.LambdaIntegration(streamingLambda.lambdaFunction, {
      proxy: true,
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

    // ===== OUTPUTS =====
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
      value: chatbotLambda.lambdaFunction.functionName,
      description: 'Lambda function name',
    });

    new cdk.CfnOutput(this, 'StreamingFunctionName', {
      value: streamingLambda.lambdaFunction.functionName,
      description: 'Streaming Lambda function name',
    });
  }
}

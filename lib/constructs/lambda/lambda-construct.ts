import { Construct } from "constructs";
import {
    Function,
    Runtime,
    Code,
    Architecture,
    Tracing,
    ILayerVersion,
} from "aws-cdk-lib/aws-lambda";
import {
    Role,
    ServicePrincipal,
    ManagedPolicy,
    PolicyStatement,
    Policy,
} from "aws-cdk-lib/aws-iam";
import { Duration } from "aws-cdk-lib";

export interface LambdaConstructProps {
    readonly functionName: string;
    readonly handler: string;
    readonly code: Code;
    readonly runtime?: Runtime;
    readonly architecture?: Architecture;
    readonly timeout?: Duration;
    readonly memorySize?: number;
    readonly environment?: { [key: string]: string };
    readonly role?: Role;
    readonly additionalPolicies?: PolicyStatement[];
    readonly tracing?: boolean;
    readonly reservedConcurrentExecutions?: number;
    readonly description?: string;
    readonly layers?: ILayerVersion[];
}

export class LambdaConstruct extends Construct {
    public readonly lambdaFunction: Function;
    public readonly lambdaRole: Role;

    constructor(scope: Construct, id: string, props: LambdaConstructProps) {
        super(scope, id);

        // Create IAM Role for Lambda
        if (props.role) {
            this.lambdaRole = props.role;
        } else {
            this.lambdaRole = new Role(this, "LambdaRole", {
                assumedBy: new ServicePrincipal("lambda.amazonaws.com"),
                managedPolicies: [ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaBasicExecutionRole")]
            });
        }

        // Additional Policies
        if (props.additionalPolicies) {
            props.additionalPolicies.forEach((policy, index) => {
                const inlinePolicy = new Policy(this, `Policy${index}`, {
                    statements: [policy],
                });
                this.lambdaRole.attachInlinePolicy(inlinePolicy);
            });
        }

        const timeout = props.timeout ?? Duration.minutes(5);
        const memorySize = props.memorySize ?? 1024;

        // Create Lambda Function
        this.lambdaFunction = new Function(this, "LambdaFunction", {
            functionName: props.functionName,
            runtime: props.runtime ?? Runtime.PYTHON_3_11,
            handler: props.handler,
            code: props.code,
            role: this.lambdaRole,
            timeout: timeout,
            memorySize: memorySize,
            architecture: props.architecture ?? Architecture.ARM_64,
            tracing: props.tracing ? Tracing.ACTIVE : Tracing.DISABLED,
            description: props.description,
            environment: props.environment,
            layers: props.layers,
            reservedConcurrentExecutions: props.reservedConcurrentExecutions,
        });
    }
}

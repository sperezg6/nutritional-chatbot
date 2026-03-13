import { Construct } from 'constructs';
import {
    Table,
    AttributeType,
    BillingMode,
    TableEncryption,
    ProjectionType,
} from 'aws-cdk-lib/aws-dynamodb';
import { RemovalPolicy } from 'aws-cdk-lib';

export interface GlobalSecondaryIndexProps {
    readonly indexName: string;
    readonly partitionKey: string;
    readonly partitionKeyType?: AttributeType;
    readonly sortKey?: string;
    readonly sortKeyType?: AttributeType;
    readonly projectionType?: ProjectionType;
}

export interface DynamoDBConstructProps {
    readonly tableName: string;
    readonly partitionKey: string;
    readonly sortKey?: string;
    readonly partitionKeyType?: AttributeType;
    readonly sortKeyType?: AttributeType;
    readonly billingMode?: BillingMode;
    readonly encryption?: TableEncryption;
    readonly removalPolicy?: RemovalPolicy;
    readonly globalSecondaryIndexes?: GlobalSecondaryIndexProps[];
}

/** A construct for creating a DynamoDB table with optional GSIs */
export class DynamoDBConstruct extends Construct {
    public readonly table: Table;
    public readonly tableName: string;

    constructor(scope: Construct, id: string, props: DynamoDBConstructProps) {
        super(scope, id);

        this.table = new Table(this, 'DynamoDBTable', {
            tableName: props.tableName,
            partitionKey: {
                name: props.partitionKey,
                type: props.partitionKeyType ?? AttributeType.STRING,
            },
            ...(props.sortKey && {
                sortKey: {
                    name: props.sortKey,
                    type: props.sortKeyType ?? AttributeType.STRING,
                },
            }),
            billingMode: props.billingMode ?? BillingMode.PAY_PER_REQUEST,
            encryption: TableEncryption.AWS_MANAGED,
            removalPolicy: props.removalPolicy ?? RemovalPolicy.RETAIN,
        });

        // Add GSIs
        if (props.globalSecondaryIndexes) {
            for (const gsi of props.globalSecondaryIndexes) {
                this.table.addGlobalSecondaryIndex({
                    indexName: gsi.indexName,
                    partitionKey: {
                        name: gsi.partitionKey,
                        type: gsi.partitionKeyType ?? AttributeType.STRING,
                    },
                    ...(gsi.sortKey && {
                        sortKey: {
                            name: gsi.sortKey,
                            type: gsi.sortKeyType ?? AttributeType.STRING,
                        },
                    }),
                    projectionType: gsi.projectionType ?? ProjectionType.ALL,
                });
            }
        }

        this.tableName = this.table.tableName;
    }
}

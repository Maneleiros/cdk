import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as iam from 'aws-cdk-lib/aws-iam';
import { DistributedMap } from 'aws-cdk-lib/aws-stepfunctions';
// import * as sqs from 'aws-cdk-lib/aws-sqs';

export class WebStaticaCdkStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const wbstbckt = new s3.Bucket(this, 'mlfmibucket3',{
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      
      });
      new s3deploy.BucketDeployment(this, 'DeployWebsite',{
        sources: [s3deploy.Source.asset('./website')],
        destinationBucket: wbstbckt,
      });
      const distribution = new cloudfront.Distribution(this, 'WebDistribution', {
        defaultBehavior:{
          origin: new origins.S3Origin(wbstbckt),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        }
      })
      wbstbckt.addToResourcePolicy(new iam.PolicyStatement ({
        actions: ['s3:GetObject'],
        resources: [wbstbckt.arnForObjects('*')],
        principals: [new iam.ServicePrincipal('cloudfront.amazonaws.com')],
        conditions: {
          StringEquals: {
            'AWS.SourceArn': `arn:aws:cloudfront::${this.account}:distribution/${distribution.distribution}`
          }
        }

    })
      )

      new cdk.CfnOutput(this, 'WebsiteURL', {
        value: 'https://'+distribution.domainName,
        description: 'La URL del sitio web',
        exportName: 'WebsiteURL',
      });
  }
}

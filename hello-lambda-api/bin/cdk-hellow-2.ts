#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { CdkHellow2Stack } from '../lib/cdk-hellow-2-stack';

const app = new cdk.App();
new CdkHellow2Stack(app, 'CdkHellow2Stack', {
  env: { account: '713881788316', region: 'eu-south-2' },

});
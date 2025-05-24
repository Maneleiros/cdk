import os
import json
import logging
import boto3
from boto3.dynamodb.types import TypeDeserializer
from redis import Redis
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

## Fleet Status attribute and values
C_STATUS_AVAILABLE = 'AVAILABLE'
C_STATUS_INUSE = 'IN_USE'
C_Status = 'Status'

## Key Scheme
C_ASSET_PREFIX = 'ASSET#'
GEO_KEY = 'assetgeo:{metro}'
BATTERY_KEY = 'assetbattery:{metro}'
C_METRO='DC'

## Boto3 Session Instantiation
session = boto3.session.Session()

## Retrive Amazon ElastiCache Credentials from Secrets Manager  
smclient = session.client(service_name='secretsmanager', region_name=session.region_name)
resp = smclient.get_secret_value(SecretId=os.environ['EC_REDIS_SECRET_NAME'])

SECRET = json.loads(resp['SecretString'])

## Setup Amazon ELastiCache for Redis client    
redis_client = Redis(
                    host=os.environ['EC_REDIS_ENDPOINT'], 
                    port=6379, 
                    password=SECRET['password'], 
                    decode_responses=True,ssl=True
                    )



def dynamo_obj_to_python_obj(dynamo_obj: dict) -> dict:
    '''
        Purpose: Deserialize DynamoDB data to Python data types
        Params:
            dynamo_obj: DynanoDB item dictionary 
        Returns:
            Dictionary of DynamoDB Item attributes cast into Python data types.
    '''
    deserializer = TypeDeserializer()
    
    return { k: deserializer.deserialize(v)  for k, v in dynamo_obj.items()} 

def synch_cache(record:dict):
    '''
        Purpose: Add/Update/Remove items to In-Memory Database
        Params:
            record: Dictionary of Item to be synchronized
        Returns:
            None
    '''
    try:
        
        geo_key = GEO_KEY.format(metro=C_METRO)
        battery_key = BATTERY_KEY.format(metro=C_METRO)
        
        if record['OP'] == 'ADD':
            
            pipe = redis_client.pipeline()
            # TODO 1: Adding bikes when 'AVAILABLE' to 'assetgeo:DC' in Redis
            # GEOADD - Add bike to geospatial key: 'assetgeo:DC'
            pipe.geoadd(geo_key,(record['Longitude'],record['Latitude'],record['asset_id']))

            # ZADD - Add bike to sorted set key: 'assetbattery:DC'
            pipe.zadd(battery_key,{record['asset_id']:record['Battery']})

            # TODO 1: Ends
            pr = pipe.execute()
            logger.info(f"Redis response:")
            logger.info(pr)
            logger.info(f"Added AssetID: {record['asset_id']} to cache key: {geo_key} with Geo-coordinates: [{record['Longitude']}.{record['Latitude']}]")
            logger.info(f"Added AssetID: {record['asset_id']} to cache key: {battery_key} with Battery: {record['Battery']}")
                
        if record['OP'] == 'REM':
    
            pipe = redis_client.pipeline()
            # TODO 2: Removing bikes from 'assetgeo:DC' and 'assetbattery:DC' when status is not 'AVAILABLE'
            # ZREM - Remove bike from sorted sets 'assetgeo:DC' and 'assetbattery:DC'
            pipe.zrem(geo_key,record['asset_id'])
            pipe.zrem(battery_key,record['asset_id'])

            # TODO 2: Ends
            pr = pipe.execute()
            logger.info(f"Redis response:")
            logger.info(pr)
            logger.info(f"Removed AssetID: {record['asset_id']} from keys: {geo_key} and {battery_key}")
            
    except:
        raise
    
    return

def process_bike_events(record: dict):
    '''
    process fleet stream events - Detect asset's 'Status' changes to AVAILABLE or IN_USE
    Params:
        record - Stream event JSON as python dictionary
    '''
    ## cache record parameter to sync cash
    cache_record = None
    ## Depending on the type of event - INSERT, REMOVE or MODIFY - Get New and Old Images of the item
    if record['dynamodb'].get('NewImage',None):
        new_image = dynamo_obj_to_python_obj(record['dynamodb']['NewImage'])
    if record['dynamodb'].get('OldImage',None):
        old_image = dynamo_obj_to_python_obj(record['dynamodb']['OldImage'])
    
    ## Get the item keys
    keys = dynamo_obj_to_python_obj(record['dynamodb']['Keys'])
    
    '''Process only if all of the below conditions are met
        ## 1. Asset items (excluding service records)
        ## 2. INSERT event: Status is in 'AVAILABLE' or 'IN_USE'
        ## 3. UPDATE event: Status changed from 'AVAILABLE' or 'IN_USE'    
    '''

    if str(keys['PK']).startswith('ASSET#') and  str(keys['SK']).startswith('ASSET#'):
        if (
                record['eventName'] == "INSERT" and new_image['Status'] in ['AVAILABLE','IN_USE']
           or
               ( record['eventName'] == "MODIFY" 
                and new_image['Status'] != old_image['Status'] 
                and new_image['Status'] in ['AVAILABLE','IN_USE'] 
               )
           ):
                ''' Get asset's attributes: Latitude, Longitude and Battery '''
                logger.info(f"AssetID: {keys['PK']} | Geo-coordinates: [{new_image['Latitude']}.{new_image['Longitude']}] | Battery: {new_image['Battery']} | Status: {new_image['Status']}")
                
                asset_id = keys['PK'].split(C_ASSET_PREFIX)[1]
                
                asset_geo_data = (new_image['Longitude'],new_image['Latitude'],asset_id)

                cache_record = {'asset_id': asset_id, 'Latitude': new_image['Latitude'], 'Longitude': new_image['Latitude'], 'Battery': int(new_image['Battery']) }
                
                if new_image['Status'] == C_STATUS_AVAILABLE:
                    cache_record['OP'] = 'ADD'
                
                if new_image['Status'] == C_STATUS_INUSE:
                    cache_record['OP'] = 'REM'

        if record['eventName'] == 'REMOVE':
            
            logger.info(f"AssetID: {keys['PK']} | Geo-coordinates: [{old_image['Latitude']}.{old_image['Longitude']}] | Battery: {old_image['Battery']} | Status: {old_image['Status']}")

            asset_id = keys['PK'].split(C_ASSET_PREFIX)[1]
            
            cache_record['OP'] = 'REM'

    if cache_record['OP']:
        synch_cache(cache_record)
    return

def lambda_handler(event, context):
    #print("Received event: " + json.dumps(event, indent=2))
    
    if redis_client.ping():
        logger.info('Successfully connected to Redis cluster.')
    
    for record in event['Records']:
        print(record['eventName'])
        print("DynamoDB Record: \n" + json.dumps(record['dynamodb']))
        try:
            process_bike_events(record)
        except:
            print(f'Unable to process trip: {json.dumps(record)}')
            raise
    logger.info('Successfully processed {} records.'.format(len(event['Records'])))
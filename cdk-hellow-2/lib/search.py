import os
import json
import logging
import boto3
from botocore.exceptions import ClientError
from typing import Optional 
from redis import Redis
import base64



logger = logging.getLogger()
logger.setLevel(logging.INFO)

## Cache key names
GEO_KEY = 'assetgeo:{city}'
BATTERY_KEY = 'assetbattery:{city}'

## Boto3 Session Instantiation
session = boto3.session.Session()
region=session.region_name

# Function - get_secret: Returns SecretString from Secrets Manager
def get_secret(secret_name):
    """
    Purpose: Return SecretString from Secrets Manager
    Params:
        secret_name - Name of Secret to retrieve
    Returns:
        SecretString
    """
    # Create a Secrets Manager client
    session = boto3.session.Session()
    region=session.region_name
    client = session.client(
        service_name='secretsmanager',
        region_name=region
    )
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            # An error occurred on the server side.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
    return get_secret_value_response['SecretString']


def geo_search_assets(lon: float, lat: float, radius: int, city: str, level: Optional[int] = None):
    '''
    Purpose: Return bikes within a given search radius of user's location. Optionally, Include only the bikes at or above the specified battery threshold.
    Params:
        lat - Search at Latitude 
        lon - Search at Longitude 
        radius - Search radius (Default: 1 miles)
        level - Battery threshold
        
    Returns:
            Array [{"AssetID": <bike>, "Distance" :<distance>, "BatteryLevel": <level>},]
    '''    
    
    # Add the Redis operations to:
    # Find available bikes within the provided search radius 
    # Optionally above a specified battery level 
    geo_key = GEO_KEY.format(city=city)
    battery_key = BATTERY_KEY.format(city=city)
    
    search_geo_key = f'search:{geo_key}:{lon}{lat}{radius}'
    search_battery_key = f'search:{battery_key}:{radius}'
    
    # Get secret from AWS Secrets Manager    
    secret = get_secret(os.environ["EC_REDIS_SECRET_NAME"])
    # convert secret json string to dictionary
    secret_dict = json.loads(secret)
    
    # host from env EC_REDIS_ENDPOINT
    host = os.environ["EC_REDIS_ENDPOINT"]
    password = secret_dict.get('password')    
        
    # Add here - Redis Client
    redis_client = Redis(host=host, port=6379, ssl=True, decode_responses=True, password=password) 
    '''
    GeoSearch and store 
    '''
    # TODO 3: Perform geospatial bike search
    redis_client.geosearchstore(
        search_geo_key,
        geo_key,
        longitude=lon,
        latitude=lat,
        unit='mi', 
        radius=radius, 
        sort='ASC', 
        count=100, ## limit to 100 results
        storedist=True
        )

    # TODO 3: Ends  
    
    '''
    Find Bikes from battery level Sorted Set
    '''
    # TODO 4: Filter bikes by battery levels
    if level:
        redis_client.zrangestore(
            search_battery_key,
            battery_key, 
            '+inf', 
            level, 
            desc=True,
            byscore=True,
            offset=0,
            num=10000 ## limit to 10000 results
            )

    # TODO 4: Ends            
    
    
    '''
    Return bikes list
    '''
    # TODO 5: Filter bikes by battery level
    if level:
        results = redis_client.zinter({search_geo_key:1,search_battery_key:0}, aggregate='max', withscores=True)
    else:
        results = redis_client.zrange(search_geo_key,0,-1,withscores=True)

    # TODO 5: Ends 
    
    #Get battery level data for the assets in the result set   
    bikes = [r[0] for r in results]
    # Augument results with battery level 
    bikes_w_battery = redis_client.zmscore(battery_key,bikes)
    
    results = [{ "AssetID":r[0], "Distance": str(round(r[1],2)), "BatteryLevel": str(bikes_w_battery[results.index(r)]) } for r in results]
    return results
    
def lambda_handler(event, context):
    
    try:
    
        query = event['queryStringParameters']
        
        results = geo_search_assets(
                        lat = query['latitude'], 
                        lon = query['longitude'], 
                        radius= query['radius'], 
                        city=query['metro'],
                        level= query['level']
                        )

        return { 
                "statusCode": 200, 
                "isBase64Encoded": "false",
                "body": json.dumps(results),
                "headers": {"access-control-allow-origin" : "*" }
                }
    
    except:
        logger.error(f'Error searching bikes!')
        raise

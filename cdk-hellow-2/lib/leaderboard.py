import os
import json
import logging
import boto3
from datetime import datetime
from redis import Redis


logger = logging.getLogger()
logger.setLevel(logging.INFO)

## Cache key names
lb_key_scheme = "lb:dl:{metro}:{month}"

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

def get_leaderboards(userid:str, metro: str, month: str, top_n: int = 20) -> dict:
    '''
        Purpose: Return leaderboard data consisting of top_n distance leaders and the calling user's rank
        Params:
            top_n: int 
                Top N riders on the leaderboard
            userid: str
                Search at Longitude 
                
        Returns:
            Array: [[(user,distance),(user,distance),],<rank>]
    '''
    
    ##get month from utc time using datetime
    
    key = lb_key_scheme.format(metro=metro,month=month)
    rc_pipe = redis_client.pipeline()
    
    # Add the Redis operations to:
    # 1. Get Top N riders from leaderboard
    # 2. Rank of calling user
    
    '''
        1. Get Top N riders from the leaderboard
    '''
    # TODO 8: Input command to get Top N riders from the leaderboard
    rc_pipe.zrange(key,'+inf',0,byscore=True,withscores=True,desc=True,offset=0,num=top_n)
    # TODO 8: Ends

    '''
        2. Rank of calling user
    '''
    # TODO 9: Input command to return the rank of the calling user
    rc_pipe.zrevrank(key,userid)
    # TODO 9: Ends

    '''
        Return results
    '''
    results = rc_pipe.execute()
    return results
    
def format_results(results) -> dict:
    '''
        Purpose: Format results for API response
        Params:
            results: Array returned by get_leaderboards()
                
        Returns:
        { 'leaderboard': [{"rank":, "userid":, "distance": },..], "user_rank": <rank> }
    '''
    
    return { 
            'leaderboard': [ {"rank": 1 + results[0].index(r), "userid": r[0], "distance": r[1] } for r in results[0] ],
            'user_rank': str(1+results[1]) if results[1] else 'Not_Ranked'
        }

def get_userid(event):
    # if this is an API gateway request use the user_id from cognito
    if "apiId" in event["requestContext"]:
        return event["requestContext"]["authorizer"]["claims"]["name"]
    # allow userid in request for testing
    return event['queryStringParameters']['userid']
    
def lambda_handler(event, context):
    
    try:
    
        redis_client.ping()
        
        logger.info('Successfully connected to Redis cluster.')
        
        ## Parse API request 
        query = event['queryStringParameters']
        
        ## Get current month format: 'MON'
        month = datetime.strftime(datetime.utcnow(),"%b")        
        
        ## Fetch leaderboard results
        results = get_leaderboards(userid=get_userid(event),metro=query['metro'],month=month.upper())
        
        ## Return leaderboard results
        return { 
                "statusCode": 200, 
                "isBase64Encoded": "false",
                "body": json.dumps(format_results(results)),
                "headers": {"access-control-allow-origin" : "*" }
                }
    
    except:
        logger.error(f'Error fetching leaderboard results!')
        raise
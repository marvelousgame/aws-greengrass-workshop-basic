#
# GGBootcampPubSub.py
#

'''
/*
 * Copyright 2010-2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License").
 * You may not use this file except in compliance with the License.
 * A copy of the License is located at
 *
 *  http://aws.amazon.com/apache2.0
 *
 * or in the "license" file accompanying this file. This file is distributed
 * on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
 * express or implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */
 '''

#
# globals
#
haveSense = None
push_interval = 1


#
# import useful stuff
#
try:
    from sense_hat import SenseHat
    haveSense = True
except:
    haveSense = False
    import random

import json
from time import gmtime, strftime
from gg_discovery_api import GGDiscovery

from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import sys
import logging
import time
import argparse


# Shadow callback
def sdwCallback(client, userdata, message):
    global push_interval
    shadow_delta_topic = '$aws/things/' + clientId + '/shadow/update/delta'
    logger.info("Shadow message on topic: " + message.topic)
    logger.info("payload: " + message.payload)

    if message.topic != shadow_delta_topic:
        return

    logger.info("shadow: message received on delta topic")
    delta = json.loads(message.payload)
    logger.info("delta: " + str(delta))
    try:
        new_push_interval = delta['state']['push_interval']
        push_interval = new_push_interval
        logger.info("new_push_interval: " + str(new_push_interval))
        state = { "state": { "reported": { "push_interval": new_push_interval }, "desired": None } }
        shadow_update_topic = '$aws/things/' + clientId + '/shadow/update'
        logger.info("reporting state to shadow: " + shadow_update_topic)
        #myAWSIoTMQTTClient.publish(shadow_update_topic, json.dumps(state, indent=4), 0)
        client.publish(shadow_update_topic, json.dumps(state, indent=4), 0)
    except Exception as e:
        logger.error("error updating shadow: " + str(e))


# Custom MQTT message callback
def customCallback(client, userdata, message):
    print("---customCallback---")
    print("client: " + str(client))
    print("userdata: " + str(userdata))
    print("Received  message on topic: " + message.topic)
    print(message.payload)
    print("--------------\n\n")


def getSensorData(sense):
    message = {}

    if sense is not None:
        message['sensor'] = 'SenseHat'
        message['temperature'] = sense.get_temperature()
        message['pressure'] = sense.get_pressure()
        message['humidity'] = sense.get_humidity()
    else:
        message['sensor'] = 'Random'
        message['temperature'] = random.uniform(15,35)
        message['pressure'] = random.uniform(30,70)
        message['humidity'] = random.uniform(900,1150)

    return message


# Read in command-line parameters
parser = argparse.ArgumentParser()
parser.add_argument("-e", "--endpoint", action="store", required=True, dest="host", help="Your AWS IoT custom endpoint")
parser.add_argument("-r", "--rootCA", action="store", required=True, dest="rootCAPath", help="Root CA file path")
parser.add_argument("-c", "--cert", action="store", dest="certificatePath", help="Certificate file path")
parser.add_argument("-k", "--key", action="store", dest="privateKeyPath", help="Private key file path")
parser.add_argument("-w", "--websocket", action="store_true", dest="useWebsocket", default=False, help="Use MQTT over WebSocket")
parser.add_argument("-id", "--clientId", action="store", dest="clientId", default="basicPubSub", help="Targeted client id")
parser.add_argument("-t", "--topic", action="store", dest="topic", default="sdk/test/Python", help="Targeted topic")
parser.add_argument("--dataformat", action="store", dest="dataFormat", default="json", help="Dataformat could be json or csv")
parser.add_argument("--connect-to", action="store", dest="connectTo", default="awsiot", help="Where to connect to. Can be either awsiot or greengrass")
parser.add_argument("--proxy-url", action="store", dest="discoveryProxyURL", default=None, help="Proxy URL for discovery")

args = parser.parse_args()
host = args.host
rootCAPath = args.rootCAPath
certificatePath = args.certificatePath
privateKeyPath = args.privateKeyPath
useWebsocket = args.useWebsocket
clientId = args.clientId
topic = args.topic
dataFormat = args.dataFormat
connectTo = args.connectTo
discoveryProxyURL = args.discoveryProxyURL

coreCAFile = "core-CAs.crt"

#
# Shadow
#
shadow_topics = '$aws/things/' + clientId + '/shadow/#'
shadow_update_topic = '$aws/things/' + clientId + '/shadow/update'
state = { "state": { "reported": { "push_interval": push_interval } } }

#
# validate cmdline args
#
if args.useWebsocket and args.certificatePath and args.privateKeyPath:
    parser.error("X.509 cert authentication and WebSocket are mutual exclusive. Please pick one.")
    exit(2)

if not args.useWebsocket and (not args.certificatePath or not args.privateKeyPath):
    parser.error("Missing credentials for authentication.")
    exit(2)

if args.dataFormat != "json" and args.dataFormat != "csv":
    parser.error("--dataformat must be either 'json' or 'csv'. Your choice was: " + args.dataFormat)
    exit(2)

if args.connectTo != "awsiot" and args.connectTo != "greengrass":
    parser.error("--connect-to must be either 'awsiot' or 'greengrass'. Your choice was: " + args.connectTo)
    exit(2)

#
# Configure logging
#
logger = logging.getLogger("AWSIoTPythonSDK.core")
logger.setLevel(logging.DEBUG)
streamHandler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)


#
# connection information when connecting to AWS IoT
#
response_document = {
    "GGGroups": [
        {
            "Cores": [
                {
                    "thingArn": "no-arn-aws-iot-connection",
                    "Connectivity": [
                        {
                            "Metadata": "",
                            "PortNumber": 8883,
                            "Id": "AWS_IoT",
                            "HostAddress": host
                        },
                    ]
                }
            ],
            "GGGroupId": "no-group-id-aws-iot-connection"
        }
    ]
}
CAFile = rootCAPath


#
# when connecting to greengrass call the discovery API
# to retrieve connectivity information for the GG core
#
if connectTo == "greengrass":
    CAFile = coreCAFile
    logger.info("connecting to GREENGRASS: starting discover")
    discovery = GGDiscovery(clientId, host, 8443, rootCAPath, certificatePath, privateKeyPath)

    # you can use a proxy in case your ggads cannot reach the internet directly
    if discoveryProxyURL is not None:
        #discovery.proxy = 'http://localhost:3128'
        discovery.proxy = discoveryProxyURL

    logger.info("discovery url: " + discovery.url)
    (status, response_document) = discovery.discovery()
    logger.info("status: " + str(status))
    logger.info("response_document: " + json.dumps(response_document, indent=4))

    if int(status) != 200:
        logger.error("status not equal 200: can not get discover information")
        sys.exit(1)

    #
    # write CAs from the discovery call to a file
    #
    try:
        f = open(coreCAFile, 'w')
        f.truncate()

        for group in response_document['GGGroups']:
            for ca in group['CAs']:
                #print ca
                f.write(ca)

        f.close()
    except Exception as e:
        logger.error("cannot write file " + coreCAFile + ": " + str(e))
        sys.exit(1)
else:
    logger.info("connecting to AWS IoT")

numGroups = len(response_document['GGGroups'])

if connectTo == "greengrass":
    logger.info("number of Greengrass Groups: " + str(numGroups))
    time.sleep(2)

logger.info("CAFile: " + CAFile)
# iterate through all connection options for the core
coreHost = ""
corePort = ""
numcoreConnections = 0
coreConnections = {}

for group in response_document['GGGroups']:
    logger.info("GGGroupId: " + group['GGGroupId'])
    for core in group['Cores']:
        myAWSIoTMQTTClient = None

        myAWSIoTMQTTClient = AWSIoTMQTTClient(clientId)

        # AWSIoTMQTTClient connection configuration
        myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
        myAWSIoTMQTTClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
        myAWSIoTMQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
        myAWSIoTMQTTClient.configureConnectDisconnectTimeout(10)  # 10 sec
        myAWSIoTMQTTClient.configureMQTTOperationTimeout(5)  # 5 sec
        myAWSIoTMQTTClient.configureCredentials(CAFile, privateKeyPath, certificatePath)

        logger.info("Core thingArn: " + core['thingArn'])
        for conn in core['Connectivity']:
            coreHost = conn['HostAddress']
            corePort = conn['PortNumber']
            logger.info("coreHost: " + coreHost + " corePort: " + str(corePort))

            myAWSIoTMQTTClient.configureEndpoint(coreHost, corePort)
            # Connect to the core and subscribe
            try:
                myAWSIoTMQTTClient.connect()
                logger.info("subscribe and set customCallback: topic: " + topic)
                myAWSIoTMQTTClient.subscribe(topic, 0, customCallback)
                time.sleep(2)
                logger.info("subscribe and set sdwCallback: topic: " + shadow_topics)
                myAWSIoTMQTTClient.subscribe(shadow_topics, 0, sdwCallback)
                time.sleep(2)
                logger.info("reporting state to shadow: " + shadow_update_topic)
                myAWSIoTMQTTClient.publish(shadow_update_topic, json.dumps(state, indent=4), 0)
                numcoreConnections += 1
                coreConnections[core['thingArn']] = myAWSIoTMQTTClient
                logger.info("connected")
                break
            except Exception as e:
                logger.warn("mqtt connect: " + str(e))

logger.info("numcoreConnections: " + str(numcoreConnections))
if numcoreConnections == 0:
    logger.error("no connection to core possible, exiting")
    sys.exit(1)
elif numcoreConnections != numGroups:
    logger.warn("not all connections to all cores could be established")


logger.info("connectioninformation")
for arn in coreConnections:
    logger.info("  " + arn + ": " + str(coreConnections[arn]))

time.sleep(2)

# sense hat
if haveSense is True:
    sense = SenseHat()
else:
    sense = None

# Publish to the same topic in a loop forever
loopCount = 0
while True:
        message = getSensorData(sense)
	if dataFormat == "csv":
		csv = ','.join((clientId, time.strftime("%Y-%m-%dT%H:%M:%S", gmtime()), str(message['temperature']), str(message['pressure']), str(message['humidity'])))
		logger.info(json.dumps(csv))
		logger.info("publish: topic: " + topic)
                for arn in coreConnections:
                    logger.info(arn)
		    coreConnections[arn].publish(topic, csv, 0)
	else:
		message['device'] = clientId
		message['datetime'] = time.strftime("%Y-%m-%dT%H:%M:%S", gmtime())
		logger.info(json.dumps(message))
		logger.info("publish: topic: " + topic)
                for arn in coreConnections:
                    message['coreArn'] = arn
                    logger.info(arn)
		    coreConnections[arn].publish(topic, json.dumps(message, indent=4), 0)

	time.sleep(push_interval)

#!/usr/bin/env python
import paho.mqtt.client as mqtt
import logging
import json
import RPi.GPIO as GPIO
import settings as Settings

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
if Settings.DEBUG:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)


def on(client, relay):
    logger.info("Turning ON relay {}".format(relay))
    GPIO.output(Settings.RELAY_TO_PIN[Settings.RELAY], GPIO.LOW)

    logger.debug("Sending MQTT ON message")
    on_dict = {
        'name': Settings.ACCESSORY_NAME,
        'service_name': Settings.SERVICE_NAME,
        'characteristic': 'On',
        'value': True
    }
    on_response = client.publish("{}/to/set".format(Settings.MQTT_TOPIC),
                                 json.dumps(on_dict))


def off(client, relay):
    logger.info("Turning OFF relay {}".format(relay))
    GPIO.output(Settings.RELAY_TO_PIN[Settings.RELAY], GPIO.HIGH)

    logger.debug("Sending MQTT OFF message")
    off_dict = {
        'name': Settings.ACCESSORY_NAME,
        'service_name': Settings.SERVICE_NAME,
        'characteristic': 'On',
        'value': False
    }
    off_response = client.publish("{}/to/set".format(Settings.MQTT_TOPIC),
                                  json.dumps(off_dict))


def on_connect(client, userdata, flags, rc):
    logger.info("Connected with result code " + str(rc))
    client.subscribe(Settings.MQTT_TOPIC + "/#")
    add_device(client)


def on_message(client, userdata, msg):
    if msg.topic == "{}/from/set/{}".format(Settings.MQTT_TOPIC,
                                            Settings.ACCESSORY_NAME):
        if json.loads(msg.payload.decode())['value']:
            on(client, Settings.RELAY)
        else:
            off(client, Settings.RELAY)


def add_device(client):
    logger.info("Adding Accessory")
    add_accessory_dict = {
        'name': Settings.ACCESSORY_NAME,
        'service_name': Settings.SERVICE_NAME,
        'service': "Switch"
    }
    add_accessory_response = client.publish(
        "{}/to/add".format(Settings.MQTT_TOPIC),
        json.dumps(add_accessory_dict))

    logger.info("Adding Service")
    add_service_dict = {
        'name': Settings.ACCESSORY_NAME,
        'service_name': Settings.SERVICE_NAME,
        'service': "Switch"
    }
    add_service_response = client.publish(
        "{}/to/add/service".format(Settings.MQTT_TOPIC),
        json.dumps(add_service_dict))


def main():
    logger.info("Started")

    logger.debug("Setting up Relay Module interface")
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(Settings.RELAY_TO_PIN[Settings.RELAY], GPIO.OUT)

    client = mqtt.Client()
    client.enable_logger(logger=logger)
    client.on_connect = on_connect
    client.on_message = on_message

    client.username_pw_set(Settings.MQTT_USER, Settings.MQTT_PASS)
    client.connect(Settings.MQTT_HOST, Settings.MQTT_PORT, 60)

    logger.debug("Starting MQTT Client loop")
    client.loop_forever()


if __name__ == "__main__":
    main()
    logger.info("Finished")

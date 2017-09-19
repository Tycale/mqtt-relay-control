#!/usr/bin/env python
import json
import logging
from threading import Timer

import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO

import settings as Settings


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
if Settings.DEBUG:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)


class VentilationUnit:
    def __init__(self, mqtt_client, relay=1):
        self.turned_on = False
        self.mqtt_client = mqtt_client
        self.relay = relay
        self.timer = None
        logger.debug("Setting up Relay Module interface")
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(Settings.RELAY_TO_PIN[self.relay], GPIO.OUT)


    @property
    def mqtt_message(self):
        return { 'name': Settings.ACCESSORY_NAME,
                 'service_name': Settings.SERVICE_NAME,
                 'characteristic': 'On',
                 'value': self.turned_on }


    def request_device(self):
        request_accessory_dict = { 'name': Settings.ACCESSORY_NAME }
        request_accessory_response = self.mqtt_client.publish(
            "{}/to/get".format(Settings.MQTT_TOPIC),
            json.dumps(request_accessory_dict))


    def check_device(self, message):
        if 'message' in message:
            if 'undefined' in message['message']:
                self.add_device()


    def add_device(self):
        logger.info("Adding Accessory")
        add_accessory_dict = {
            'name': Settings.ACCESSORY_NAME,
            'service_name': Settings.SERVICE_NAME,
            'service': "Switch"
        }
        add_accessory_response = self.mqtt_client.publish(
            "{}/to/add".format(Settings.MQTT_TOPIC),
            json.dumps(add_accessory_dict))

        logger.info("Adding Service")
        add_service_dict = {
            'name': Settings.ACCESSORY_NAME,
            'service_name': Settings.SERVICE_NAME,
            'service': "Switch"
        }
        add_service_response = self.mqtt_client.publish(
            "{}/to/add/service".format(Settings.MQTT_TOPIC),
            json.dumps(add_service_dict))

    def turn_on(self):
        logger.info("Turning ON relay {}".format(self.relay))
        GPIO.output(Settings.RELAY_TO_PIN[self.relay], GPIO.LOW)
        self.turned_on = True

        timer_seconds = Settings.TIMER_MINUTES * 60
        self.timer = Timer(timer_seconds, self.turn_off)
        logger.info("Starting timer for {} minutes".format(Settings.TIMER_MINUTES))
        self.timer.start()

        logger.debug("Sending MQTT ON message")
        self.mqtt_client.publish("{}/to/set".format(Settings.MQTT_TOPIC),
                                     json.dumps(self.mqtt_message))


    def turn_off(self):
        logger.info("Turning OFF relay {}".format(self.relay))
        GPIO.output(Settings.RELAY_TO_PIN[self.relay], GPIO.HIGH)
        self.turned_on = False

        if self.timer:
            logger.info("Cancelling off Timer")
            self.timer.cancel()

        logger.debug("Sending MQTT OFF message")
        self.mqtt_client.publish("{}/to/set".format(Settings.MQTT_TOPIC),
                                      json.dumps(self.mqtt_message))


def on_connect(client, userdata, flags, rc):
    logger.info("Connected with result code " + str(rc))
    client.subscribe(Settings.MQTT_TOPIC + "/#")
    userdata['ventilation'].request_device()


def on_message(client, userdata, msg):
    if msg.topic == "{}/from/set/{}".format(Settings.MQTT_TOPIC,
                                            Settings.ACCESSORY_NAME):
        if json.loads(msg.payload.decode())['value']:
            userdata['ventilation'].turn_on()
        else:
            userdata['ventilation'].turn_off()
    elif msg.topic == "{}/from/response/{}".format(Settings.MQTT_TOPIC,
                                            Settings.ACCESSORY_NAME):
        userdata['ventilation'].check_device(json.loads(msg.payload.decode()))


def main():
    logger.info("Started")

    client = mqtt.Client()
    client.enable_logger(logger=logger)
    client.on_connect = on_connect
    client.on_message = on_message

    client.username_pw_set(Settings.MQTT_USER, Settings.MQTT_PASS)
    client.connect(Settings.MQTT_HOST, Settings.MQTT_PORT, 60)

    logger.debug("Creating Ventilation Unit object")
    ventilation = VentilationUnit(client, relay=Settings.RELAY)
    client.user_data_set({'ventilation': ventilation})

    logger.debug("Starting MQTT Client loop")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        client.disconnect()


if __name__ == "__main__":
    main()
    logger.info("Finished")

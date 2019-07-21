#!/usr/bin/env python
import json
import logging
from threading import Timer

import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


class MQTTRelay:
    def __init__(self,
                 mqtt_client,
                 mqtt_settings,
                 accessory_name,
                 service_name,
                 pins,
                 timeout=False):
        self.mqtt_client = mqtt_client
        self.mqtt_settings = mqtt_settings
        self.mqtt_topic = mqtt_settings['topic']
        self.accessory_name = accessory_name
        self.service_name = service_name
        self.pins = pins
        self.timeout = timeout

        self.turned_on = False
        self.timer = None

        logger.debug("Setting up Relay GPIO on pins {}".format(self.pins))
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        for pin in self.pins:
            GPIO.setup(pin, GPIO.OUT)

    @property
    def mqtt_message(self):
        return {
            'name': self.accessory_name,
            'service_name': self.service_name,
            'characteristic': 'On',
            'value': self.turned_on
        }

    def request_device(self):
        request_accessory_dict = {'name': self.accessory_name}
        request_accessory_response = self.mqtt_client.publish(
            "{}/to/get".format(self.mqtt_topic),
            json.dumps(request_accessory_dict))

    def check_device(self, message):
        if 'message' in message:
            if 'undefined' in message['message']:
                self.add_device()

    def add_device(self):
        logger.info("Adding Accessory")
        add_accessory_dict = {
            'name': self.accessory_name,
            'service_name': self.service_name,
            'service': "Switch"
        }
        add_accessory_response = self.mqtt_client.publish(
            "{}/to/add".format(self.mqtt_topic),
            json.dumps(add_accessory_dict))

        logger.info("Adding Service")
        add_service_dict = {
            'name': self.accessory_name,
            'service_name': self.service_name,
            'service': "Switch"
        }
        add_service_response = self.mqtt_client.publish(
            "{}/to/add/service".format(self.mqtt_topic),
            json.dumps(add_service_dict))

    def remove_device(self):
        logger.info("Removing Service {}".format(self.service_name))
        remove_service_dict = {
            'name': self.accessory_name,
            'service_name': self.service_name,
        }
        remove_service_response = self.mqtt_client.publish(
            "{}/to/remove/service".format(self.mqtt_topic),
            json.dumps(remove_service_dict))

        logger.info("Removing Accessory {}".format(self.accessory_name))
        remove_accessory_dict = {
            'name': self.accessory_name,
        }
        remove_accessory_response = self.mqtt_client.publish(
            "{}/to/remove".format(self.mqtt_topic),
            json.dumps(remove_accessory_dict))

    def turn_on(self):
        logger.info("Turning ON relay on pins {}".format(self.pins))
        for pin in self.pins:
            GPIO.output(pin, GPIO.LOW)
        self.turned_on = True

        if self.timeout:
            timer_seconds = self.timeout * 60
            self.timer = Timer(timer_seconds, self.turn_off)
            logger.info("Starting timer for {} minutes".format(self.timeout))
            self.timer.start()

        logger.debug("Sending MQTT ON message")
        self.update_mqtt_state()

    def turn_off(self):
        logger.info("Turning OFF relay on pins {}".format(self.pins))
        for pin in self.pins:
            GPIO.output(pin, GPIO.HIGH)
        self.turned_on = False

        if self.timer:
            logger.info("Cancelling off Timer")
            self.timer.cancel()
            self.timer = None

        logger.debug("Sending MQTT OFF message")
        self.update_mqtt_state()

    def update_mqtt_state(self):
        if self.mqtt_settings['homebridge_protocol']:
            self.mqtt_client.publish("{}/to/set".format(self.mqtt_topic),
                                 json.dumps(self.mqtt_message))
        if self.mqtt_settings['plain_mqtt']:
            msg_state = "ON" if self.turned_on else "OFF"
            self.mqtt_client.publish("{}/state/{}".format(self.mqtt_topic,
                self.accessory_name), msg_state)


def on_connect(client, userdata, flags, rc):
    logger.info("Connected with result code " + str(rc))
    client.subscribe(userdata['mqtt']['topic'] + "/#")
    for relay in userdata['relays']:
        relay.request_device()


def on_message(client, userdata, msg):
    if userdata['mqtt']['homebridge_protocol']:
        on_message_homebridge(client, userdata, msg)
    if userdata['mqtt']['plain_mqtt']:
        on_message_plain(client, userdata, msg)

def on_message_plain(client, userdata, msg):
    prefix, action, accessory_name = msg.topic.split('/')
    if action == 'command' :
        relay_index = find_relay_index(accessory_name, userdata)
        if "on" in msg.payload.lower():
            userdata['relays'][relay_index].turn_on()
        else:
            userdata['relays'][relay_index].turn_off()

def on_message_homebridge(client, userdata, msg):
    action_for_accessory = check_action_for_accessory(msg.topic, userdata)
    if action_for_accessory:
        relay_index = find_relay_index(action_for_accessory[1], userdata)
        if action_for_accessory[0] == "set":
            logger.info(
                "{} message for accessory {}".format(*action_for_accessory))
            if json.loads(msg.payload.decode())['value']:
                userdata['relays'][relay_index].turn_on()
            else:
                userdata['relays'][relay_index].turn_off()
        elif action_for_accessory[0] == "response":
            logger.info(
                "{} message for accessory {}".format(*action_for_accessory))
            userdata['relays'][relay_index].check_device(
                json.loads(msg.payload.decode()))


def check_action_for_accessory(topic, userdata):
    our_topics = [
        "{}/from/{}/{}".format(userdata['mqtt']['topic'], action,
                               r.accessory_name)
        for r in userdata['relays'] for action in ('set', 'response')
    ]
    if topic in our_topics:
        return (topic.split('/')[2], topic.split('/')[3])
    return False


def find_relay_index(accessory_name, userdata):
    for index, relay in enumerate(userdata['relays']):
        if relay.accessory_name == accessory_name:
            return index


def main():
    logger.info("Started")
    try:
        with open("settings.json") as settings_file:
            settings = json.load(settings_file)
    except OSError:
        logger.error("Error loading settings file")
        return

    if settings['debug']:
        logger.setLevel(logging.DEBUG)

    client = mqtt.Client()
    client.enable_logger(logger=logger)
    client.on_connect = on_connect
    client.on_message = on_message

    client.username_pw_set(settings['mqtt']['username'],
                           settings['mqtt']['password'])
    client.connect(settings['mqtt']['host'], settings['mqtt']['port'], 60)

    logger.debug("Creating MQTT Relay object(s)")
    relays = []
    for switch in settings['switches']:
        relay_obj = MQTTRelay(client, settings['mqtt'], **switch)
        relays.append(relay_obj)
    client.user_data_set({'relays': relays, 'mqtt': settings['mqtt']})

    logger.debug("Starting MQTT Client loop")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        for relay in relays:
            relay.remove_device()
        client.disconnect()


if __name__ == "__main__":
    main()
    logger.info("Finished")

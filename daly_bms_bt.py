#!/usr/bin/python3
# Added some data points as of this link
# https://diysolarforum.com/threads/decoding-the-daly-smartbms-protocol.21898/

import time
import argparse
import json
import asyncio
import multiprocessing
from modules import DalyBMSBluetooth
from modules import Logger
from modules import get_logger
from modules import ERROR_CODES

parser = argparse.ArgumentParser()
parser.add_argument("--bt", help="Use BT mac address", type=str, required=True)
parser.add_argument("--loop", help="Pause between loop runs in s, default 10s",
                    type=int,
                    default=10)
parser.add_argument("--mqtt", help="Write output to MQTT", action="store_true")
parser.add_argument("--mqtt-topic", 
                    help="MQTT topic to write to, default DalySmartBMS", 
                    type=str,
                    default="DalySmartBMS")
parser.add_argument("--mqtt-broker", 
                    help="MQTT broker (server), default localhost", 
                    type=str,
                    default="localhost")
parser.add_argument("--mqtt-port", 
                    help="MQTT port, default 1883", 
                    type=int,
                    default=1883)
parser.add_argument("--mqtt-user", 
                    help="Username to authenticate MQTT with", 
                    type=str,
                    default="")
parser.add_argument("--mqtt-password", 
                    help="Password to authenticate MQTT with", 
                    type=str,
                    default="")
args = parser.parse_args()

logger = get_logger(level='info')
received_data = False
if args.bt:
    mac_address = args.bt
time.sleep(1)

if args.mqtt:
    import paho.mqtt.client as paho
    mqtt_client = paho.Client()
    mqtt_client.enable_logger(logger)
    mqtt_client.username_pw_set(args.mqtt_user, args.mqtt_password)
    mqtt_client.connect(args.mqtt_broker, port=args.mqtt_port)

def mqtt_single_out(topic, data, retain=True):
    logger.info(f'Send data: {data} on topic: {topic}, retain flag: {retain}')
    mqtt_client.publish(topic, data, retain=retain)

def mqtt_iterator(result, base=''):
    if base == '':
        base = "/" + result[0] + "/" + result[1]
        mqtt_single_out(f'{args.mqtt_topic}{base}/time', result[2])
    for key in result[3].keys():
        if type(result[3][key]) == dict:
            logger.info(f'Result dict: {base}')
            mqtt_iterator(result[3][key], f'{base}/{key}')
        else:
            if type(result[3][key]) == list:
                val = json.dumps(result[3][key])
            else:
                val = result[3][key]
            mqtt_single_out(f'{args.mqtt_topic}{base}/{key}', val)

def print_result(result):
    if args.mqtt:
        mqtt_iterator(result)
    else:
        print(json.dumps(result, indent=2))

class DalyBMSConnection():
    def __init__(self, mac_address, logger):
        self.logger = logger
        self.bt_bms = DalyBMSBluetooth(logger=logger)
        self.mac_address = mac_address
        self.last_data_received = None

    async def connect(self):
        await self.bt_bms.connect(mac_address=self.mac_address)

    async def _data_point(self, measurement, data):
        self.logger.debug(data)
        if not data:
            logger.warning("failed to receive status on %s" % measurement)
            return
        point = [measurement,
                self.mac_address,
                time.time(),
                data]
        print_result(point)
        self.last_data_received = time.time()
        return point

async def main(con):
    logger.info("Connecting")
    await con.connect()
    logger.info("Starting loop")
    received_data = False
    while con.bt_bms.client.is_connected:
        logger.debug("run start")
        await con._data_point("Status", await con.bt_bms.get_status())
        await con._data_point("SOC", await con.bt_bms.get_soc())
        await con._data_point("CellVoltages", await con.bt_bms.get_cell_voltages())
        await con._data_point("MOSFetStatus", await con.bt_bms.get_mosfet_status())
        await con._data_point("Temperatures", await con.bt_bms.get_temperatures())
        await con._data_point("TemperatureRange", await con.bt_bms.get_temperature_range())
        await con._data_point("CellVoltageRange", await con.bt_bms.get_cell_voltage_range())
        await con._data_point("CellBalancingStatus", await con.bt_bms.get_balancing_status())
        await con._data_point("ErrorStatus", await con.bt_bms.get_errors())
        await con._data_point("SoftwareVersion", await con.bt_bms.get_hw_sw_version("Software"))
        await con._data_point("HardwareVersion", await con.bt_bms.get_hw_sw_version("Hardware"))
        await con._data_point("CellAlarmVoltages", await con.bt_bms.get_alarm_voltages("Cell"))
        await con._data_point("PackAlarmVoltages", await con.bt_bms.get_alarm_voltages("Pack"))
        await con._data_point("DiffAlarmsTempVolt", await con.bt_bms.get_alarms_diff_temp_volt())
        await con._data_point("LoadChargeAlarms", await con.bt_bms.get_alarms_load_charge())
        await con._data_point("RatedNominals", await con.bt_bms.get_rated_nominals())
        await con._data_point("BalanceSettings", await con.bt_bms.get_balance_settings())
        await con._data_point("ShortShutdownAmpsInternalOhms", await con.bt_bms.get_short_shutdownamp_ohm())

        if con.last_data_received is None:
            logger.warning("Failed receive data")
            await asyncio.sleep(10)
            continue
        time_diff = time.time() - con.last_data_received
        if time_diff > 30:
            logger.error("BMS thread didn't receive data for %0.1f seconds" % time_diff)
        else:
            if not received_data:
                logger.info("First received data")
                received_data = True
        logger.debug("run done")
        await asyncio.sleep(args.loop)
    await con.bt_bms.disconnect()
    logger.info("Loop ended")

con = DalyBMSConnection(mac_address, logger=logger)
loop = asyncio.get_event_loop()
asyncio.ensure_future(main(con))
try:
    loop.run_forever()
except KeyboardInterrupt:
    pass

loop.run_until_complete(con.bt_bms.disconnect())

if args.mqtt:
    mqtt_client.disconnect()

logger.info("Final End")
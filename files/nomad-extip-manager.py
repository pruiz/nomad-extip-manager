#!python3

import os
import requests
import nomad
import subprocess
import logging
import time
import ipaddress
import textwrap

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set up Nomad client
#n = nomad.Nomad(host="localhost", port=4646)
n = nomad.Nomad(host=os.getenv("NOMAD_ADDR", "localhost"), port=4646, cert=(os.getenv("NOMAD_CLIENT_CERT"), os.getenv("NOMAD_CLIENT_KEY")), verify=False)

TARGET_TAG = "EXTERNAL_IP"
RECONNECT_DELAY = 5
NODE = "pmxc-111"
SHELL = "/bin/cat"
#SHELL = "/bin/bash"
SCRIPT = f"""
# First create our chains if there are not yet there. In reverse order.
for CHAIN in AFTER_EXTERNAL_IP EXTERNAL_IP; do
	if ! iptables -w --numeric -t nat --list $CHAIN >/dev/null 2>&1; then
		iptables -w -t nat -N $CHAIN
		iptables -w -t nat -A $CHAIN -j RETURN
		iptables -w -t nat -I POSTROUTING -j $CHAIN
	fi
done
"""


def setup_nat_rule(intip, extip):
	script = SCRIPT + textwrap.dedent(f"""\
	# Remove (possibly) stale/old rules
	for line in $(iptables --line-numbers --numeric -t nat --list EXTERNAL_IP | awk '($5 == "{intip}" && $7 != "to:{extip}") {{print $1}}' | tac); do
		iptables -w -t nat -D EXTERNAL_IP $line
	done

	# Add the new rule (if not already present)
	iptables -w -t nat -C EXTERNAL_IP -s {intip} -j SNAT --to-source {extip} \
			|| \
	iptables -w -t nat -I EXTERNAL_IP -s {intip} -j SNAT --to-source {extip}
	""")
	process = subprocess.Popen([SHELL], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
	stdout, stderr = process.communicate(input=script)

	if process.returncode != 0:
		raise Exception(f"Error setting up NAT rule: {stderr}")

	logger.debug(f"STDOUT: {stdout}")
	logger.info(f"Successfully set up NAT rule for {intip} -> {extip}")

def clear_nat_rules(intip):
	script = SCRIPT + textwrap.dedent(f"""\
	# Remove (possibly) stale/old rules
	for line in $(iptables --line-numbers --numeric -t nat --list EXTERNAL_IP | awk '($5 == "{intip}") {{print $1}}' | tac); do
		iptables -w -t nat -D EXTERNAL_IP $line
	done
	""")
	process = subprocess.Popen([SHELL], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
	stdout, stderr = process.communicate(input=script)

	if process.returncode != 0:
		raise Exception(f"Error setting up NAT rule: {stderr}")

	logger.debug(f"STDOUT: {stdout}")
	logger.info(f"Successfully cleared up NAT rules for {intip}")


def handle_events_(message):
	for event in message.get('Events'):
		topic = event.get('Topic')

		if topic != 'Allocation': # or topic == 'Job':
			logging.warning(f"Skipping event with topic {topic}")
			return

		allocation = event.get('Payload', {}).get('Allocation', {})
		jobid = allocation.get('JobID')
		nodeid = allocation.get('NodeID')
		nodename = allocation.get('NodeName')
		taskgroup = allocation.get('TaskGroup')
		desiredstatus = allocation.get('DesiredStatus')
		clientstatus = allocation.get('ClientStatus')
		taskstates = allocation.get('TaskStates')
		networkstatus = allocation.get('NetworkStatus', {})
		networkaddress = networkstatus.get('Address', None)

		logger.info(f"Received event from {nodename} for {jobid}/{taskgroup}: {desiredstatus} ({clientstatus})")

		#if jobid != "vicky-agent":
		#	logger.debug(f"Skipping job {jobid}")
		#	return

		if not networkaddress:
			logger.info(f"Job has no NetworkStatus.Address: {networkaddress}")
			return

		if clientstatus not in ['pending', 'running', 'complete']:
			logger.debug(f"Skipping client status {clientstatus}")
			return

		job = n.job.get_job(jobid)
		groups = job.get('TaskGroups', [])
		group = next(filter(lambda x: x.get('Name') == taskgroup, groups), {})
		meta = group.get('Meta', {})
		extip = meta.get(TARGET_TAG, None)

		if not extip:
			logger.debug(f"Job has no extip meta, skipping..")
			return

		# if extip starts with '${' then make interpolation..
		if extip.startswith('${'):
			node = n.node.get_node(nodeid)
			if extip.startswith('${meta.'):
				key = extip.split('.')[1].strip('}')
				extip = node.get('Meta', {}).get(key, None)
			else:
				logger.error(f"Unsupported interpolation: {extip}")
				return

		logger.info(f"ExtIP ==> {extip}")

		# Ensure is a valid IP Address
		ipaddress.ip_address(extip)

		if clientstatus in ['pending', 'running']:
			logger.info(f"Setting up NAT rule for {networkaddress} -> {extip}")
			setup_nat_rule(networkaddress, extip)
		elif clientstatus == 'complete':
			logger.info(f"Clearing NAT rule for {networkaddress}")
			clear_nat_rules(networkaddress)

#		for taskname, data in taskstates.items():
#			state = data.get('State')
#			if state != 'running':
#				logger.debug(f"Skipping task {taskname} with state {state}")
#
#			# Get the tasks tags from jobs api
#			job = n.job.get_job(jobid)
#			groups = job.get('TaskGroups', [])
#			group = next(filter(lambda x: x.get('Name') == taskgroup, groups), {})
#			task = next(filter(lambda x: x.get('Name') == taskname, group.get('Tasks', [])), {})
#			#.get(taskgroup, {}).get('Tasks', {}).get(taskname)
#			logger.debug(f"==> {jobid}/{taskgroup}/{taskname}: {task}")
#
#			# Ensure task group is using 'bridge' networking mode..
#			network_mode = next(iter(group.get('Networks', []))).get('Mode', None)
#
#			if network_mode != 'bridge':
#				logger.debug(f"Skipping task group {taskgroup} with network mode {network_mode}")
#				return
#
#			# Get the task's env
#			env = task.get('Env', {})
#			logger.debug(f"==> {jobid}/{taskgroup}/{taskname}: {env}")


def handle_events(message):
	try:
		handle_events_(message)
	except Exception as e:
		logger.exception(f"Error handling event: {e}")

def subscribe_to_events():
	while True:
		try:
			logger.info("Starting event subscription...")
			stream, cancellator, messages = n.event.stream.get_stream(topic={'Allocation': "*"})
			stream.daemon = True
			stream.start()
			while True:
				message = messages.get()
#				logger.info(f"Received message: {message}")
				handle_events(message)
#				print(event)
				#events.task_done()
		except (nomad.api.exceptions.BaseNomadException, nomad.api.exceptions.URLNotFoundNomadException) as e:
			logger.exception(f"Nomad error: {e}. Retrying in {RECONNECT_DELAY} seconds...")
			time.sleep(RECONNECT_DELAY)
		except Exception as e:
			logger.exception(f"Unexpected error: {e}. Retrying in {RECONNECT_DELAY} seconds...")
			time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
	subscribe_to_events()

# vim: set syntax=python sts=2 ts=2 sw=2 et ai: #

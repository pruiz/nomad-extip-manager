# First create our chains if there are not yet there. In reverse order.
for CHAIN in AFTER_EXTERNAL_IP EXTERNAL_IP; do
	if ! iptables -w --numeric -t nat --list $CHAIN >/dev/null 2>&1; then
		iptables -w -t nat -N $CHAIN
		iptables -w -t nat -A $CHAIN -j RETURN
	fi
done

ts=`date +%s`

iptables -t nat -S POSTROUTING | head -n 2 | grep -F -- '-j EXTERNAL_IP' && exit 0 	#< If jump rule exists (at 1st position), we are done
iptables -t nat -I POSTROUTING 1 -m comment --comment "NEIM:$ts" -j EXTERNAL_IP 	#< Insert jump to our target (at 1st position)
while iptables -t nat -D POSTROUTING -j EXTERNAL_IP >/dev/null 2>&1; do :; done		#< Delete (potential) existing jump rule w/o signature

# Erasing legacy nomad-extip-manager and docker-extip-manager rules...
for sig in `iptables -S POSTROUTING -t nat | grep -Fv "NEIM:$ts" | grep -o 'NEIM:[0-9]\+'`
do
	iptables -t nat -D POSTROUTING -j EXTERNAL_IP -m comment --comment "$sig"
done

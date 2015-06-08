import sys
import json


filterword = "queue"
logname = "test.log"
if len(sys.argv) > 1:
    logname = sys.argv[1]
    if len(sys.argv) > 2:
        filterword = sys.argv[2]

fdata = {}

for line in open(logname):
    if line.startswith("---"):
        continue
    data, _, nextdata = line.partition("template")
    while len(nextdata) > 0:
        data, _, nextdata = nextdata.partition("template")
        data = json.loads(data)
        for node, value in data.items():
            for group, cs in value.items():
                for c in cs.keys():
                    if filterword in c:
                        val = data[node][group][c]
                        if isinstance(val, dict):
                            val = float(val["sum"])/val["avgcount"]
                        nodedata = fdata.setdefault(node, {})
                        groupdata = nodedata.setdefault(group, {})
                        if c not in groupdata:
                            groupdata[c] = {}
                            groupdata[c]["sum"] = val
                            groupdata[c]["count"] = 1
                            groupdata[c]["avg"] = val
                            groupdata[c]["max"] = val
                            groupdata[c]["min"] = val
                        else:
                            groupdata[c]["sum"] += val
                            groupdata[c]["count"] += 1
                            s = float(groupdata[c]["sum"]) 
                            groupdata[c]["avg"] = s / groupdata[c]["count"]
                            if val > groupdata[c]["max"]:
                                groupdata[c]["max"] = val
                            if val < groupdata[c]["min"]:
                                groupdata[c]["min"] = val


for nodedata in fdata.values():
    for groups in nodedata.values():
        for cs in groups.values():
            cs.pop("sum")
            cs.pop("count")

with open("res", "w") as res:
    res.write(json.dumps(fdata, indent=2))

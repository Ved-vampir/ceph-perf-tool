import re
import sys
import json

import texttable


filterok = ["queue", "latency"]
filterno = ["max", "min"]

logname = "test.log"

if len(sys.argv) > 1:
    logname = sys.argv[1]
    # if len(sys.argv) > 2:
    #     filterword = sys.argv[2]

def natural_sort(l):
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return sorted(l, key=alphanum_key)


def ok(word, filter_ok, filter_no):
    for item in filter_no:
        if item in word:
            return False
    for item in filter_ok:
        if item in word:
            return True
    return False



def filter_data():
    fdata = {}
    saved = {}

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
                        if ok(c, filterok, filterno):
                            val = data[node][group][c]
                            if isinstance(val, dict):
                                oldval = saved.setdefault(node+group+c, [0, 0])
                                s = val["sum"]-oldval[0]
                                n = val["avgcount"]-oldval[1]
                                saved[node+group+c] = [val["sum"], val["avgcount"]]
                                if n != 0:
                                    val = float(s)/(n)
                                else:
                                    val = 0.0
                                
                                # if val["avgcount"] != 0:
                                #     val = float(val["sum"])/val["avgcount"]
                                # else:
                                #     val = 0.0
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
                                if groupdata[c]["count"] != 0:
                                    groupdata[c]["avg"] = s / groupdata[c]["count"]
                                else:
                                    groupdata[c]["avg"] = 0.0
                                if val > groupdata[c]["max"]:
                                    groupdata[c]["max"] = val
                                if val < groupdata[c]["min"]:
                                    groupdata[c]["min"] = val
    return fdata

def save_results(fdata):
    header = {}

    rowkeys = [key for key in natural_sort(fdata.keys()) if "osd" in key]
    for nodedata in fdata.values():
        for name, groups in nodedata.items():
            line = header.setdefault(name, set())
            for cn, cs in groups.items():
                cs.pop("sum")
                cs.pop("count")
                if cs["avg"] != 0:
                    line.add(cn)

    tdata = {key: [] for key in header.keys()}
    for rowkey in rowkeys:
        nodedata = fdata[rowkey]
        for group, counters in header.items():
            newrow = [rowkey.split(".")[1]]
            for counter in counters:
                if group in nodedata:
                    frmt = "max: {0[max]:.5f}\nmin: {0[min]:.5f}\navg: {0[avg]:.5f}"
                    newrow.append(frmt.format(nodedata[group][counter]))
                else:
                    newrow.append('')
            tdata[group].append(newrow)

    for group, value in tdata.items():
        tab = texttable.Texttable(1000)
        tab.set_deco(tab.HEADER | tab.VLINES | tab.BORDER | tab.HLINES)
        cur_header = ["osd / {0}".format(group)]
        cur_header.extend(header[group])
        tab.add_row(cur_header)
        tab.header = cur_header
        for row in value:
            tab.add_row(row)
        with  open("res_table_{0}".format(group), "w") as res:
            res.write(tab.draw())


    with open("res_json", "w") as res:
        res.write(json.dumps(fdata, indent=2))




save_results(filter_data())


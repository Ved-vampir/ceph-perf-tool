import re
import os
import sys
import json

import texttable


filterok = ["queue", "latency"]
filterno = ["max", "min"]

schema = {"avg": {"format": "[{0[avg]:.3g}, {0[dev]:.3g}]", "header": "[avg, dev]"},
          "per": {"format": "[{0[p50]:.3g}, {0[p95]:.3g}]", "header": "[50%, 95%]"},
          "other": {"format": "[{0[max]:.3g}, {0[min]:.3g}, {0[avg]:.3g}]", "header": "[max, min, avg]"}}

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


def get_type(name):
    avg_metrics = ["queue"]
    per_metrics = ["latency"]
    for m in avg_metrics:
        if m in name:
            return "avg"
    for m in per_metrics:
        if m in name:
            return "per"
    return "other"



def med_dev(vals, med):
    dev = ((sum(abs(med - i) ** 2 for i in vals) / len(vals)) ** 0.5)
    return dev


def percetile(vals, p):
    indf = p * len(vals) / 100.0
    ind = int(round(indf))
    if indf == ind:
        # print len(vals), ind
        return (vals[ind - 1] + vals[ind]) / 2.0
    else:
        return vals[ind - 1]


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
                            # if c == "commitcycle_latency" and "7" in node:
                            #     print val
                            nodedata = fdata.setdefault(node, {})
                            groupdata = nodedata.setdefault(group, {})
                            if c not in groupdata:
                                groupdata[c] = {}
                                groupdata[c]["sum"] = val
                                groupdata[c]["count"] = 1
                                groupdata[c]["avg"] = val
                                groupdata[c]["max"] = val
                                groupdata[c]["min"] = val
                                groupdata[c]["val"] = [val]
                            else:
                                groupdata[c]["sum"] += val
                                groupdata[c]["count"] += 1
                                groupdata[c]["val"].append(val)
                                if val > groupdata[c]["max"]:
                                    groupdata[c]["max"] = val
                                if val < groupdata[c]["min"] and val > 0:
                                    groupdata[c]["min"] = val
    return fdata

def save_results(fdata):
    if not os.path.exists("resses"):
        os.mkdir("resses")
    header = {}

    rowkeys = [key for key in natural_sort(fdata.keys()) if "osd" in key]
    for nodedata in fdata.values():
        for name, groups in nodedata.items():
            line = header.setdefault(name, set())
            for cn, cs in groups.items():
                # compute avg etc
                s = float(cs["sum"])
                if cs["count"] != 0:
                    cs["avg"] = s / cs["count"]
                else:
                    cs["avg"] = 0.0
                cs["dev"] = med_dev(cs["val"], cs["avg"])
                pdata = sorted(cs["val"])
                cs["p50"] = percetile(pdata, 50)
                cs["p95"] = percetile(pdata, 95)
                # del common data
                cs.pop("sum")
                cs.pop("count")
                if cs["avg"] != 0:
                    # hl = get_type(cn)
                    line.add(cn)

    tdata = {key: [] for key in header.keys()}
    for rowkey in rowkeys:
        nodedata = fdata[rowkey]
        for group, counters in header.items():
            newrow = [rowkey.split(".")[1]]
            for counter in counters:
                if group in nodedata:
                    frmt = schema[get_type(counter)]["format"]
                    newrow.append(frmt.format(nodedata[group][counter]))
                else:
                    newrow.append('')
            tdata[group].append(newrow)

    for group, value in tdata.items():
        tab = texttable.Texttable(1000)
        tab.set_deco(tab.HEADER | tab.VLINES | tab.BORDER | tab.HLINES)
        cur_header = ["osd / {0}".format(group)]
        cur_header.extend("{0}\n{1}".format(h, schema[get_type(h)]["header"])
                          for h in header[group])
        tab.add_row(cur_header)
        tab.header = cur_header
        for row in value:
            tab.add_row(row)
        with  open("resses/res_table_{0}".format(group), "w") as res:
            res.write(tab.draw())


    with open("resses/res_json", "w") as res:
        res.write(json.dumps(fdata, indent=2))




save_results(filter_data())


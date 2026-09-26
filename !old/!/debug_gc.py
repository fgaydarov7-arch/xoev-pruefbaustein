import xml.etree.ElementTree as ET

NS_XOEV_CL = "http://xoev.de/schemata/genericode/4"
path = "shemas/xauslaender/codeliste/Aufenthaltsstatus_9.xml"
tree = ET.parse(path)
root = tree.getroot()

col_set = root.find("ColumnSet")
print("ColumnSet:", col_set)
if col_set is None:
    print("ABORT: no ColumnSet")
    exit()

keys = col_set.findall("Key")
print("Keys count:", len(keys))
for k in keys:
    print("  Key Id:", k.get("Id"))
    ann_path = "Annotation/AppInfo/{%s}recommendedKeyColumn" % NS_XOEV_CL
    found = k.find(ann_path)
    print("  recommendedKeyColumn found:", found is not None)
    col_ref = k.find("ColumnRef")
    print("  ColumnRef Ref:", col_ref.get("Ref") if col_ref is not None else None)

scl = root.find("SimpleCodeList")
print("SimpleCodeList:", scl)
if scl is None:
    print("ABORT: no SimpleCodeList")
    exit()

rows = scl.findall("Row")
print("Rows count:", len(rows))
if rows:
    for v in rows[0].findall("Value"):
        sv = v.find("SimpleValue")
        print("  ColumnRef=%s val=%s" % (v.get("ColumnRef"), sv.text if sv is not None else None))

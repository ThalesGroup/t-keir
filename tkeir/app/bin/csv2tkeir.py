import pandas as pd
import os
import argparse
import json
import errno

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python  2.5
        if exc.errno != errno.EEXIST or (not os.path.isdir(path)):
            raise

def add_kg_item(subject, prop, value):
    kg_item={
        "subject": {
            "content": subject,
            "lemma_content": "",
            "label": "",
            "class": -1,
            "positions": -1,
        },
        "property": {
            "content": prop,
            "lemma_content": prop,
            "label": "",
            "class": -1,
            "positions": [-1],
        },
        "value": {
            "content": value,
            "lemma_content": value,
            "label": "",
            "class": -1,
            "positions": [-1],
        },
        "automatically_fill": True,
        "confidence": 0.0,
        "weight": 0.0,
        "field_type": "named-entity",
    }
    return kg_item

def main(args):                
    df = pd.read_csv(args.input,sep=";",encoding="utf-8")
    df.fillna("",inplace=True)
    mkdir_p(args.output)
    kg_columns=[]
    object_pos=[]
    if args.kg:
        kg_columns = args.kg.split(",")
    if args.object_position:
        object_pos=args.object_position.split(",")
    count_row=0
    for index, row in df.iterrows():        
        if args.prune:
            if count_row>=args.prune:
                break
        document={
                    "data_source":"csv-convert",
                    "source_doc_id":args.input+"/"+str(index),
                    "title": "",
                    "content":"",                    
                    "kg":[],
                    "error":False
        }
        
        if args.content:
            contents=args.content.split(",")
            for kc in contents:
                if str(row[kc]) != "nan":
                    document["content"] = document["content"]+" "+str(row[kc])
            document["content"] = document["content"].strip()
        if args.title:
            titles=args.title.split(",")
            for kt in titles:
                document["title"] = document["title"]+ " " + str(row[kt])
                
            document["title"] = document["title"].strip()
        for kg_item_col in kg_columns:            
            document["kg"].append(add_kg_item(row[kg_item_col],"rel:is_a",kg_item_col))
        if args.object_position:
            if "," in row[object_pos[0]]:
                row[object_pos[0]] = row[object_pos[0]].replace(",",".")
            if "," in row[object_pos[1]]:
                row[object_pos[1]] = row[object_pos[1]].replace(",",".")
            document["position"]=[float(row[object_pos[0]]),float(row[object_pos[1]])]
        if args.object_date:
            if "T00:00:00" not in row[args.object_date]:
                row[args.object_date]=str(row[args.object_date])+"T00:00:00"
            document["date"]=row[args.object_date]
        
        
        with open(os.path.join(args.output, str(index)+".json"),"w",encoding="utf-8") as output_f:
            json.dump(document,output_f,indent=2, sort_keys=True, ensure_ascii=False)
            output_f.close()
        count_row = count_row+1
        
if __name__ == "__main__":    
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", default=None, type=str, help="csv-file")
    parser.add_argument("--title", default=None, type=str, help="title columns separated by comma")
    parser.add_argument("--content", default=None, type=str, help="content columns separated by comma")
    parser.add_argument("--kg", default=None, type=str, help="kg columns separated by comma")
    parser.add_argument("--object-position", default=None, type=str, help="object position")
    parser.add_argument("--object-date", default=None, type=str, help="event date")
    parser.add_argument("--prune", default=0, type=int, help="kg columns separated by comma")
    parser.add_argument("-o", "--output", default="out", type=str, help="output directory")
    main(parser.parse_args())
    

import pandas as pd
df = pd.read_csv("drugLibTrain_raw.tsv",sep="\t")
df.to_csv("data.csv",index=False)
df.columns


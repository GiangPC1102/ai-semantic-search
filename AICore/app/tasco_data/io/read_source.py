from pathlib import Path

import pandas as pd


def load_poi_dataset(file_path: str | Path, sheet_name: str = "POI_Dataset") -> list[dict]:
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")

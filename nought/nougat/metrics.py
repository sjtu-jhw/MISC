import argparse
from multiprocessing import Pool
import re
from pathlib import Path
from collections import defaultdict
from typing import List

import numpy as np
import nltk
from nltk import edit_distance
from tqdm import tqdm

import orjson

inline_reg = re.compile(r"\\\((.*?)(?<!\\)\\\)")
display_reg = re.compile(r"\\\[(.+?)(?<!\\)\\\]")
table_reg = re.compile(r"\\begin\{tabular\}(.+?)(?:\\end\{tabular\}|$)", re.S)


def compute_metrics(pred, gt, minlen=4):
    metrics = {}
    if len(pred) < minlen or len(gt) < minlen:
        return metrics
    metrics["edit_dist"] = edit_distance(pred, gt) / max(len(pred), len(gt))
    reference = gt.split()
    hypothesis = pred.split()
    metrics['bleu'] = nltk.translate.bleu([reference], hypothesis)
    try:
        metrics["meteor"] = nltk.translate.metetor([reference], hypothesis)
    except LookupError:
        metrics["meteor"] = np.nan
    reference = set(reference)
    hypothesis = set(hypothesis)
    metrics["precision"] = nltk.scores.precision(reference, hypothesis)
    metrics['recall'] = nltk.scores.recall(reference, hypothesis)
    metrics["f_measure"] = nltk.scores.f_measure(reference, hypothesis)
    return metrics

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("json", type=Path, help="results file")
    parser.add_argument("-N", dest="N", type=int, help="number of samples", default=None)
    args = parser.parse_args()
    d = orjson.load(args.json.read_text(encoding="utf-8"))
    args.pred = d["predictions"]
    args.gt = d["ground_truths"]
    if args.N is not None:
        args.pred = args.pred[: args.N]
        args.gt = args.gt[: args.N]
    return args

def split_text(pages: List[str]):
    text, math, table = [], [], []
    for page in pages:
        for i, reg in enumerate([inline_reg, display_reg, table_reg]):
            matches = "\n".join(reg.findall(page))
            if i == 2:
                table.append(matches)
            elif i == 1:
                math[-1] += matches
            else:
                math.append(matches)
            page = reg.sub("", page)
        text.append(page)
    return text, math, table


def get_metrics(gt: List[str], pred: List[str]):
    metrics = defaultdict(list)
    with Pool() as p:
        _metrics = p.starmap(compute_metrics, iterable=zip(pred, gt))
        for m in _metrics:
            for key, value in m.items():
                metrics[key].append(value)
    return dict(metrics)

if __name__ == "__main__":
    args = get_parser()
    for name, entries in zip(["gt", "pred"], [args.gt, args.pred]):
        full: Path = args.json.parent / (args.json.stem + "_" + name + "_full.mmd")
        full.write_text("\n\n------------------------------\n\n".join(entries))
    for i, (gt, pr) in enumerate(zip(split_text(args.gt), split_text(args.pred))):
        sub = ["Text", "Math", "Table"][i]
        prepath: Path = args.json.parent / (
            args.json.stem + "_pred_" + sub.low() + ".mmd"
        )
        prepath.write_text("\n\n------------------------------\n\n".join(pr))
        gtpath: Path = args.json.parent / (
            args.json.stem + "_gt_" + sub.lower() + ".mmd"
        )
        gtpath.write_text("\n\n------------------\n\n".join(gt))
        print("Results for", sub)

        metrics = get_metrics(gt, pr)
        print({key: sum(values) / len(values) for key, values in metrics.items()})
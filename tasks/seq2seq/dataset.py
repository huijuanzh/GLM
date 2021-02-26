import os
import torch
import torch.utils.data
import numpy as np
from tasks.data_utils import InputExample
from tqdm import tqdm
from utils import print_rank_0
import random


def gigaword_detokenize(string, is_target=False):
    # string = string.replace("UNK", "[UNK]")
    # string = string.replace("<unk>", "[UNK]")
    string = string.replace("UNK", "<unk>")
    return string


def cnndm_detokenize(string, is_target=False):
    _tok_dict = {"(": "-LRB-", ")": "-RRB-",
                 "[": "-LSB-", "]": "-RSB-",
                 "{": "-LCB-", "}": "-RCB-"}
    if not is_target:
        string = string.replace("<S_SEP>", "")
    else:
        string = string.replace("<S_SEP>", "[SEP]")
    for key, value in _tok_dict.items():
        string = string.replace(value, key)
    string = string.replace("''", "\"")
    string = string.replace("``", "\"")
    string = string.replace("`", "'")
    string = string.replace(" n't", "n't")
    string = string.replace(" 's", "'s")
    string = string.replace(" 'd", "'d")
    string = string.replace(" 'll", "'ll")
    return string


class Seq2SeqDataset(torch.utils.data.Dataset):
    def __init__(self, args, split, tokenizer):
        task, data_dir = args.task.lower(), args.data_dir
        max_src_length, max_tgt_length = args.src_seq_length, args.tgt_seq_length
        if split == "train":
            filename = "train"
        elif split == "dev":
            filename = "val"
        elif split == "test":
            filename = "test"
        else:
            raise NotImplementedError(split)
        print_rank_0(f"Creating {task}-{split} dataset from {data_dir}")
        self.dataset_name = split
        if task == "gigaword":
            detokenizer = gigaword_detokenize
        elif task == "cnn_dm":
            detokenizer = cnndm_detokenize
        else:
            detokenizer = None
        source_texts, target_texts = [], []
        with open(os.path.join(data_dir, f"{filename}.source")) as file:
            for line in file:
                line = line.strip()
                line = detokenizer(line) if detokenizer else line
                source_texts.append(line)
        with open(os.path.join(data_dir, f"{filename}.target")) as file:
            for line in file:
                line = line.strip()
                line = detokenizer(line, is_target=True) if detokenizer else line
                target_texts.append(line)
        assert len(source_texts) == len(target_texts)
        self.examples, self.samples = {}, []
        num_source_truncated, num_target_truncated = 0, 0
        cls_id = tokenizer.get_command('ENC').Id
        mask_token = 'gMASK' if args.task_mask else 'MASK'
        mask_id = tokenizer.get_command(mask_token).Id
        pad_id = tokenizer.get_command('pad').Id
        sop_id = tokenizer.get_command('sop').Id
        eop_id = tokenizer.get_command('eop').Id
        for idx, (source_text, target_text) in enumerate(zip(source_texts, target_texts)):
            breakpoint()
            if (idx + 1) % 20000 == 0:
                print_rank_0(f"Complete {idx + 1} examples")
            guid = "%s-%s" % (split, idx)
            source_truncated, target_truncated = False, False
            meta = {"ref": tokenizer.DecodeIds(tokenizer.EncodeAsIds(target_text).tokenization)}
            example = InputExample(guid=guid, text_a=source_text, text_b=target_text, meta=meta)
            self.examples[guid] = example
            source_tokens = tokenizer.EncodeAsIds(" " + source_text).tokenization
            prompt = [cls_id, mask_id] + tokenizer.EncodeAsIds(" Content:").tokenization
            if len(source_tokens) > max_src_length - len(prompt):
                source_tokens = source_tokens[:max_src_length - len(prompt)]
                source_truncated = True
            source_tokens = prompt + source_tokens
            if len(source_tokens) < max_src_length:
                source_tokens = source_tokens + [pad_id] * (max_src_length - len(source_tokens))
            sep = len(source_tokens)
            position_ids = list(range(len(source_tokens)))
            block_position_ids = [0] * len(source_tokens)
            mask_pos = source_tokens.index(mask_id)
            if split == 'train':
                target_tokens = tokenizer.EncodeAsIds(" " + target_text).tokenization
                target_tokens = target_tokens + [eop_id]
                if len(target_tokens) > max_tgt_length:
                    target_tokens = target_tokens[:max_tgt_length]
                    target_truncated = True
                loss_mask = [1] * len(target_tokens)
                if len(target_tokens) < max_tgt_length:
                    loss_mask += [0] * (max_tgt_length - len(target_tokens))
                    target_tokens += [pad_id] * (max_tgt_length - len(target_tokens))
                tokens = source_tokens + [sop_id] + target_tokens[:-1]
                loss_mask = [0] * len(source_tokens) + loss_mask
                target_ids = [0] * len(source_tokens) + target_tokens
                position_ids += [mask_pos] * len(target_tokens)
                block_position_ids += list(range(1, len(target_tokens) + 1))
                position_ids = [position_ids, block_position_ids]
                sample = {'text': np.array(tokens, dtype=np.int64), 'target': np.array(target_ids, dtype=np.int64),
                          'attention_mask': np.array(sep, dtype=np.int64),
                          'loss_mask': np.array(loss_mask, dtype=np.int64),
                          "position_id": np.array(position_ids, dtype=np.int64), "uid": guid}
                self.samples.append(sample)
            else:
                tokens = source_tokens + [sop_id]
                position_ids = position_ids + [mask_pos]
                block_position_ids = block_position_ids + [1]
                position_ids = [position_ids, block_position_ids]
                sample = {'text': np.array(tokens, dtype=np.int64), 'attention_mask': np.array(sep, dtype=np.int64),
                          "position_id": np.array(position_ids, dtype=np.int64), "uid": guid}
                self.samples.append(sample)
            if source_truncated:
                num_source_truncated += 1
            if target_truncated:
                num_target_truncated += 1
        print_rank_0(
            f"Return {len(self.samples)} {split} examples, {num_source_truncated} examples source truncated, {num_target_truncated} examples target truncated")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]

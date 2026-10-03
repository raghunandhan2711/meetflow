"""Prepare official Whisper base weights for faster-Whisper, without a Hub login.

Uses OpenAI's published checkpoint and tokenizer, verifies the checkpoint SHA256,
and maps the original layers into CTranslate2's documented Whisper specification.
Run after installing requirements-audio.txt. Assets stay inside .runtime/models.
"""
import ast
import base64
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / '.runtime' / 'models'
DESTINATION = CACHE / 'base'
CHECKSUM = 'ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e'
SOURCE = 'https://raw.githubusercontent.com/openai/whisper/main/whisper/'


def download(url, destination):
    if destination.exists():
        return
    temporary = destination.with_suffix(destination.suffix + '.partial')
    print('Downloading ' + destination.name, flush=True)
    try:
        with urllib.request.urlopen(url, timeout=90) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def byte_symbols():
    values = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
    result = {byte: chr(byte) for byte in values}
    next_code = 256
    for byte in range(256):
        if byte not in result:
            result[byte] = chr(next_code)
            next_code += 1
    return result


def tokenizer():
    from tokenizers import Tokenizer, Regex, models, pre_tokenizers, decoders
    ranks = {base64.b64decode(token): int(rank) for token, rank in
             (line.split() for line in (CACHE / 'multilingual.tiktoken').read_bytes().splitlines())}
    symbols = byte_symbols()
    text = lambda token: ''.join(symbols[byte] for byte in token)
    vocabulary = {text(token): rank for token, rank in ranks.items()}
    merges = []
    for token, rank in sorted(ranks.items(), key=lambda item: item[1]):
        parts = [bytes([byte]) for byte in token]
        while len(parts) > 2:
            candidates = [(ranks.get(parts[i] + parts[i + 1], float('inf')), i) for i in range(len(parts) - 1)]
            pair_rank, index = min(candidates)
            if pair_rank >= rank:
                break
            parts[index:index + 2] = [parts[index] + parts[index + 1]]
        if len(parts) == 2:
            merges.append((text(parts[0]), text(parts[1])))
    tree = ast.parse((CACHE / 'tokenizer-source.py').read_text(encoding='utf-8'))
    languages = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == 'LANGUAGES' for target in node.targets))
    special = ['<|endoftext|>', '<|startoftranscript|>']
    special += [f'<|{code}|>' for code in list(languages)[:99]]
    special += ['<|translate|>', '<|transcribe|>', '<|startoflm|>', '<|startofprev|>', '<|nospeech|>', '<|notimestamps|>']
    timestamps = [f'<|{index * .02:.2f}|>' for index in range(1501)]
    tokens = [token for token, _ in sorted(vocabulary.items(), key=lambda item: item[1])] + special + timestamps
    vocabulary.update({token: index for index, token in enumerate(tokens)})
    result = Tokenizer(models.BPE(vocabulary, merges))
    pattern = Regex(r"'s|'t|'re|'ve|'m|'ll|'d| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+")
    result.pre_tokenizer = pre_tokenizers.Sequence([
        pre_tokenizers.Split(pattern, behavior='isolated'), pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False)])
    result.decoder = decoders.ByteLevel()
    result.add_special_tokens(special)
    result.add_tokens(timestamps)
    return result, tokens


def convert():
    import numpy as np
    import torch
    from ctranslate2.specs.whisper_spec import WhisperSpec
    checkpoint = torch.load(CACHE / 'base.pt', map_location='cpu', weights_only=True)
    dims, state = checkpoint['dims'], checkpoint['model_state_dict']
    value = lambda key: state[key].float().numpy()
    spec = WhisperSpec(dims['n_audio_layer'], dims['n_audio_head'], dims['n_text_layer'], dims['n_text_head'])

    def linear(layer, prefix):
        layer.weight = value(prefix + '.weight')
        if prefix + '.bias' in state:
            layer.bias = value(prefix + '.bias')

    def norm(layer, prefix):
        layer.gamma, layer.beta = value(prefix + '.weight'), value(prefix + '.bias')

    def attention(layer, prefix, self_attention):
        names = ['query', 'key', 'value']
        groups = [names] if self_attention else [names[:1], names[1:]]
        for output, group in zip(layer.linear, groups):
            weights = [value(prefix + '.' + name + '.weight') for name in group]
            output.weight = np.concatenate(weights, axis=0)
            output.bias = np.concatenate([value(prefix + '.' + name + '.bias') if prefix + '.' + name + '.bias' in state
                                          else np.zeros(weight.shape[0], dtype=np.float32)
                                          for name, weight in zip(group, weights)])
        linear(layer.linear[-1], prefix + '.out')

    linear(spec.encoder.conv1, 'encoder.conv1')
    linear(spec.encoder.conv2, 'encoder.conv2')
    spec.encoder.position_encodings.encodings = value('encoder.positional_embedding')
    norm(spec.encoder.layer_norm, 'encoder.ln_post')
    spec.decoder.embeddings.weight = value('decoder.token_embedding.weight')
    spec.decoder.projection.weight = value('decoder.token_embedding.weight')
    spec.decoder.position_encodings.encodings = value('decoder.positional_embedding')
    norm(spec.decoder.layer_norm, 'decoder.ln')
    for side in ['encoder', 'decoder']:
        for index, layer in enumerate(getattr(spec, side).layer):
            prefix = f'{side}.blocks.{index}'
            attention(layer.self_attention, prefix + '.attn', True)
            norm(layer.self_attention.layer_norm, prefix + '.attn_ln')
            if side == 'decoder':
                attention(layer.attention, prefix + '.cross_attn', False)
                norm(layer.attention.layer_norm, prefix + '.cross_attn_ln')
            linear(layer.ffn.linear_0, prefix + '.mlp.0')
            linear(layer.ffn.linear_1, prefix + '.mlp.2')
            norm(layer.ffn.layer_norm, prefix + '.mlp_ln')
    encoded, tokens = tokenizer()
    assert len(tokens) == dims['n_vocab'], 'Tokenizer and checkpoint vocabularies differ.'
    spec.register_vocabulary(tokens)
    spec.config.suppress_ids = []
    spec.config.suppress_ids_begin = [220, 50257]
    spec.config.lang_ids = list(range(50259, 50358))
    spec.config.alignment_heads = [(layer, head) for layer in range(dims['n_text_layer'] // 2, dims['n_text_layer'])
                                   for head in range(dims['n_text_head'])]
    spec.validate()
    spec.optimize(quantization='int8')
    DESTINATION.mkdir(parents=True, exist_ok=True)
    spec.save(str(DESTINATION))
    encoded.save(str(DESTINATION / 'tokenizer.json'))
    print('Official Whisper base prepared for local faster-Whisper transcription.', flush=True)


if __name__ == '__main__':
    CACHE.mkdir(parents=True, exist_ok=True)
    download(f'https://openaipublic.azureedge.net/main/whisper/models/{CHECKSUM}/base.pt', CACHE / 'base.pt')
    if hashlib.sha256((CACHE / 'base.pt').read_bytes()).hexdigest() != CHECKSUM:
        raise RuntimeError('Checkpoint checksum mismatch. Remove base.pt and rerun.')
    download(SOURCE + 'assets/multilingual.tiktoken', CACHE / 'multilingual.tiktoken')
    download(SOURCE + 'tokenizer.py', CACHE / 'tokenizer-source.py')
    convert()

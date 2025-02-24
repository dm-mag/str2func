#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
'''
    Author: d.p.
    Create: 21.02.2025
    Description: Creating a database of functions for hash string literals from C/C++ code
'''
from clang.cindex import Index, CursorKind, TokenKind
import argparse
import os.path
from pathlib import Path
import time
import pickle
import signal
import xxhash

interrupt = False

def signal_handler(signum, frame):
    global interrupt
    """Handler for SIGINT signal (Ctrl+C)"""
    print('\nCtrl+C pressed, interrupted...')
    interrupt = True

def save_db(db, filename):
    # Use highest protocol for fastest pickle
    with open(filename, 'wb') as f:
        pickle.dump(db, f, protocol=pickle.HIGHEST_PROTOCOL)

def save_all():
    save_db(db,args.strdb)
    save_db(fdb,args.filesdb)

def load_db(filename):
    if os.path.exists(filename):
        with open(filename, 'rb') as f:
            return pickle.load(f)
    return {}

def load_fdb(filename):
    if os.path.exists(filename):
        with open(filename, 'rb') as f:
            return pickle.load(f)
    return set()

def get_hash(s):
    """Calculate hash for a string using last 8 bytes of MD5"""
    # return hashlib.md5(s.encode('utf-8')).digest()[-8:]
    return xxhash.xxh64_digest(s)

files_number = 0
files_size = 0

def get_file_hash_xx(filename, blocksize=65536):
    """Calculate xxHash of file using blocks"""
    global files_number, files_size
    hasher = xxhash.xxh64()
    files_number += 1
    with open(filename, 'rb') as f:
        for block in iter(lambda: f.read(blocksize), b''):
            hasher.update(block)
            files_size += len(block)
    return hasher.digest()

def get_cpp_files(path):
    """Get list of all C/C++ files in path"""
    path = Path(path)
    if path.is_file():
        return [path] if path.suffix in ['.c', '.cpp'] else []
    elif path.is_dir():
        return [f for f in path.rglob('*.[cp]*') if f.suffix in ['.c', '.cpp']]
    return []

def process_path(path):
    """Process file or directory"""
    # Create Index once before processing files
    index = Index.create()
    
    # Get list of all files first
    files = get_cpp_files(path)
    total_files = len(files)
    
    if not total_files:
        print(f"No C/C++ files found in {path}")
        return
    
    print(f"\nFound {total_files} files to process")
    
    def process_file(filepath, file_num):
        global save_time
        print(f"[{(file_num / total_files) * 100:3.1f}%] {filepath}", end=' ')
        
        fhash = get_file_hash_xx(filepath)
        if fhash in fdb:
            print("already done")
            return
        
        for node in index.parse(filepath).cursor.walk_preorder():
            if node.kind == CursorKind.FUNCTION_DECL:
                func_name = node.spelling
                
                for s in (token.spelling[1:-1] for token in node.get_tokens()
                    if token.kind == TokenKind.LITERAL and token.spelling.startswith('"')
                    and len(token.spelling) > 12):
                    hash_value = get_hash(s)
                    if hash_value not in db:
                        db[hash_value] = {func_name}
                    else:
                        db[hash_value].add(func_name)

        fdb.add(fhash)
        curr_time = time.perf_counter()
        print(f'{len(db)} {curr_time - start_time:.2f}s')
        
        # Save every 30 minutes
        if curr_time - save_time > args.savetime:
            save_all()
            save_time = time.perf_counter()
    
    # Process files with progress tracking
    for i, file_path in enumerate(files, 1):
        if interrupt:
            print("\nInterrupted by user")
            break
        process_file(str(file_path), i)
    
    # Print final statistics
    kb_size = files_size / 1024
    elapsed_time = time.perf_counter() - start_time
    print(f'\nProcessed {files_number} files {kb_size:.2f} KB')
    print(f'Speed: {files_number/elapsed_time:.2f} Fps {kb_size/elapsed_time:.1f} KBps')

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Create a database of string literals from C/C++ code')
    parser.add_argument('--version', action='version', version='%(prog)s 1.0')
    parser.add_argument('--strdb', type=str, help='database file to write results',default="str2func.db")
    parser.add_argument('--filesdb', type=str, help='database file with files hashes',default="fh.db")
    parser.add_argument('--savetime', type=int, help='time (s) to auto save databases',default=1800)
    
    subparsers = parser.add_subparsers(dest='cmd', help='Commands')
    
    # Parser for parse command
    parse_parser = subparsers.add_parser('parse', help='Parse C/C++ file')
    parse_parser.add_argument('--restart', action='store_true', help='clear databases on start')
    parse_parser.add_argument('input_file', type=str, help='Input file to process')

    # Parser for find command
    find_parser = subparsers.add_parser('find', help='Find func by string')
    find_parser.add_argument('string', type=str, help='String')

    # Parser for print command
    print_parser = subparsers.add_parser('print', help='Print database content')

    print_parser = subparsers.add_parser('info', help='Print database info')

    args = parser.parse_args()

    if args.cmd == 'parse' and args.restart:
        db = {}
        fdb = set()
    else:
        db = load_db(args.strdb)
        fdb = load_fdb(args.filesdb)

    match args.cmd:
        case 'parse':
            signal.signal(signal.SIGINT, signal_handler)
            start_time = time.perf_counter()
            save_time = start_time
            process_path(args.input_file)
            save_all()
            print(f"Database size: {len(db)} elapsed: {time.perf_counter() - start_time:.2f}s")
            
        case 'find':
            hash_value = get_hash(args.string)
            if hash_value in db:
                print(f"Found in functions: {db[hash_value]}")
            else:
                print("String not found")
            
        case 'print':
            for hash_value, functions in db.items():
                print(f"{hash_value.hex()}:{functions}")
            print('-' * 40)
            print(f"Database size: {len(db)}")
                
        case 'info':
            print(f"Database size: {len(db)}")

        case _:
            print("Unknown command. Use --help for usage information.")

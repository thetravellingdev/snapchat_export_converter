import os
import re
from collections import defaultdict
import argparse
from typing import Dict, List, Set

class PatternAnalyzer:
    def __init__(self):
        self.patterns = defaultdict(set)
        
    def extract_pattern(self, filename: str) -> str:
        """
        Convert a filename into a pattern by:
        1. Replacing dates with <date>
        2. Replacing UUIDs with <uuid>
        3. Replacing base64-like strings with <base64>
        4. Preserving file extensions
        """
        # Split filename and extension
        base, ext = os.path.splitext(filename)
        
        # Replace date patterns (YYYY-MM-DD)
        base = re.sub(r'\d{4}-\d{2}-\d{2}', '<date>', base)
        
        # Replace UUIDs
        base = re.sub(r'[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}', '<uuid>', base, flags=re.IGNORECASE)
        
        # Replace base64-like strings (sequence of alphanumeric and special chars)
        base = re.sub(r'[A-Za-z0-9+/=_-]{20,}', '<base64>', base)
        
        # Replace numeric sequences
        base = re.sub(r'\d+', '<num>', base)
        
        return f"{base}{ext}"

    def analyze_directory(self, path: str, max_depth: int = -1) -> Dict[str, Set[str]]:
        """
        Recursively analyze directory and collect file patterns.
        Returns a dictionary of directory paths to sets of patterns.
        """
        if max_depth == 0:
            return {}

        for root, dirs, files in os.walk(path):
            rel_path = os.path.relpath(root, path)
            if rel_path == '.':
                rel_path = ''
                
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            # Analyze files in current directory
            for filename in files:
                if not filename.startswith('.'):  # Skip hidden files
                    pattern = self.extract_pattern(filename)
                    self.patterns[rel_path].add(pattern)
            
            # If max_depth is specified, remove directories that would exceed it
            if max_depth > 0:
                current_depth = len(rel_path.split(os.sep)) if rel_path else 0
                if current_depth >= max_depth:
                    dirs.clear()

        return dict(self.patterns)

    def print_tree(self, path: str, max_depth: int = -1):
        """
        Print directory structure with file patterns in a tree-like format.
        """
        patterns = self.analyze_directory(path, max_depth)
        
        def print_patterns(patterns_dict: Dict[str, Set[str]], prefix: str = '', is_last: bool = True):
            for idx, (dir_path, dir_patterns) in enumerate(sorted(patterns_dict.items())):
                is_current_last = idx == len(patterns_dict) - 1
                
                # Print directory name
                if dir_path:
                    print(f"{prefix}{'└── ' if is_current_last else '├── '}{os.path.basename(dir_path)}/")
                    new_prefix = prefix + ('    ' if is_current_last else '│   ')
                else:
                    new_prefix = prefix
                
                # Print patterns
                sorted_patterns = sorted(dir_patterns)
                for pattern_idx, pattern in enumerate(sorted_patterns):
                    is_pattern_last = pattern_idx == len(sorted_patterns) - 1
                    print(f"{new_prefix}{'└── ' if is_pattern_last else '├── '}{pattern}")

        print(f"{os.path.basename(path)}/")
        print_patterns(patterns)

def main():
    parser = argparse.ArgumentParser(description='Analyze file patterns in directories')
    parser.add_argument('path', help='Path to analyze')
    parser.add_argument('--max-depth', type=int, default=-1, 
                      help='Maximum depth to traverse (-1 for unlimited)')
    args = parser.parse_args()

    analyzer = PatternAnalyzer()
    analyzer.print_tree(args.path, args.max_depth)

if __name__ == '__main__':
    main()

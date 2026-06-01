#!/usr/bin/env python3
"""
Report on emails that have not been labeled by the classifier.

This utility script reads the processed log and identifies emails that didn't
match any of the configured label rules. Useful for reviewing what emails need
new filter rules.

Usage:
    python report_unlabeled_emails.py                    # Show summary and first 20
    python report_unlabeled_emails.py --all              # Show all unlabeled emails
    python report_unlabeled_emails.py --limit 50         # Show first 50
    python report_unlabeled_emails.py --output report.txt # Save to file
"""

import json
import argparse
from pathlib import Path
from datetime import datetime


def load_processed_log(log_path):
    """Load the processed log from the specified path."""
    with open(log_path, 'r') as f:
        return json.load(f)


def get_unlabeled_emails(log):
    """Extract emails with no applied labels from the log."""
    unlabeled = []
    for md5, entry in log.items():
        if len(entry.get('applied_labels', [])) == 0:
            unlabeled.append({
                'sender': entry.get('sender', 'Unknown'),
                'subject': entry.get('email_title', 'No Subject'),
                'timestamp': entry.get('timestamp', 'Unknown'),
                'email_id': entry.get('email_id', 'Unknown')
            })
    
    # Sort by timestamp, most recent first
    unlabeled.sort(key=lambda x: x['timestamp'], reverse=True)
    return unlabeled


def format_report(unlabeled, limit=None):
    """Format the unlabeled emails as a readable report."""
    lines = []
    
    total = len(unlabeled)
    lines.append("=" * 100)
    lines.append(f"UNLABELED EMAILS REPORT")
    lines.append(f"Total: {total} emails without labels")
    lines.append("=" * 100)
    lines.append("")
    
    display_count = limit if limit else total
    emails_to_show = unlabeled[:display_count]
    
    for i, email in enumerate(emails_to_show, 1):
        lines.append(f"{i}. {email['subject']}")
        lines.append(f"   From: {email['sender']}")
        lines.append(f"   ID: {email['email_id']}")
        lines.append(f"   Time: {email['timestamp']}")
        lines.append("")
    
    if limit and total > limit:
        lines.append(f"... and {total - limit} more emails")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Report on unlabeled emails from the Gmail labeler log'
    )
    parser.add_argument(
        '--log',
        type=str,
        default='automations/gmail-labeler/data/processed_log.json',
        help='Path to the processed log file'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='Number of emails to display (default: 20)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Show all unlabeled emails (ignores --limit)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Save report to file instead of printing'
    )
    
    args = parser.parse_args()
    
    # Resolve the log path relative to the workspace root
    log_path = Path(args.log)
    if not log_path.is_absolute():
        # Try to find it relative to current directory
        if not log_path.exists():
            # Try from the workspace root
            workspace_root = Path(__file__).parent.parent.parent.parent
            log_path = workspace_root / args.log
    
    if not log_path.exists():
        print(f"Error: Log file not found at {log_path}")
        return 1
    
    # Load and process the log
    log = load_processed_log(log_path)
    unlabeled = get_unlabeled_emails(log)
    
    # Generate report
    limit = None if args.all else args.limit
    report = format_report(unlabeled, limit)
    
    # Output
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(report)
        print(f"Report saved to {output_path}")
    else:
        print(report)
    
    return 0


if __name__ == '__main__':
    exit(main())

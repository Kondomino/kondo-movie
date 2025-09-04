import argparse
from rich import print

from account.stytch_mgr import stytch_client

def main():
    # Parse Args
    parser = argparse.ArgumentParser(description='Stytch Client')
    parser.add_argument('-s', '--search', action='store_true', help='Search action')
    
    parser.add_argument('-e', '--email', type=str, help='Email address')
    
    args = parser.parse_args()
    if args.search:
        stytch_user_info = stytch_client.search(email=args.email)
        print(stytch_user_info)

if __name__ == '__main__':
    main()
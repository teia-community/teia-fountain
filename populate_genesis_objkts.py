from pytezos import Key
from pytezos import pytezos
import os
import time
import os.path
import requests
from googleapiclient.discovery import build
from google.oauth2 import service_account

# If modifying these scopes, delete the file data/token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# The ID and range of a sample spreadsheet.
FOUNTAIN_SPREADSHEET_ID = '1fcMoCMw44mZvA2qR84Bdxfi90b0AEfINflPdiBqU3kg'
FOUNTAIN_RANGE_NAME = 'Form Responses 1!A2:I'

# Address: tz1UqhPnVXdPccrVsa5khscwCLHTF2Q2CAer
key = Key.from_encoded_key(os.environ['TEIA_FOUNTAIN_KEY'], os.environ['TEIA_FOUNTAIN_PASS'])
pytezos = pytezos.using(shell='mainnet', key=key)
acct_id = pytezos.key.public_key_hash()
acct = pytezos.account()

def get_genesis(acct_id):
    url = f'https://api.tzkt.io/v1/bigmaps/522/keys?sort.asc=id&value.issuer={acct_id}&limit=1'
    r = requests.get(url)
    if r.status_code != 200:
        time.sleep(1)
        return get_genesis(acct_id)
    data = r.json()
    if len(data) > 0:
        return data[0]['key']
    return ''

def store_results(service, row_num, objkt_id):
    values = [
            [ "https://teia.art/objkt/%s" % objkt_id ]
            ]
    body = { 'values': values }
    range_name = 'Form Responses 1!I%s:I%s' % (row_num, row_num)
    #print(range_name)
    result = service.spreadsheets().values().update(
        spreadsheetId=FOUNTAIN_SPREADSHEET_ID, range=range_name,
        valueInputOption='USER_ENTERED', body=body).execute()
    print('{0} cells updated.'.format(result.get('updatedCells')))

def main():
    creds = None
    # The file data/token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('credentials.json'):
        creds = service_account.Credentials.from_service_account_file(
            'credentials.json', scopes=SCOPES)

    service = build('sheets', 'v4', credentials=creds)

    # Call the Sheets API
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=FOUNTAIN_SPREADSHEET_ID,
                                range=FOUNTAIN_RANGE_NAME).execute()
    values = result.get('values', [])

    if not values:
        print('No data found.')
    else:
        row_num = 1
        for row in values:
            row_num += 1
            if row[1] == '':
                break
            #print(row)
            address = row[1].strip()
            approved = len(row) >= 8
            #print('%s, %s' % (address, approved))
            if approved:
                if len(row[7]) == 0:
                    continue
                if len(row) >= 9:
                    if len(row[8]) > 0:
                        continue
                objkt = get_genesis(address)
                if objkt:
                    print('%s minted %s' % (address, objkt))
                    store_results(service, row_num, objkt)

if __name__ == '__main__':
    main()

import json
from discord_webhook import DiscordWebhook
from pytezos import Key, pytezos
from pytezos.rpc.node import RpcError
from pytezos.operation.result import OperationResult
from decimal import Decimal
import datetime
import os
import time
import os.path
from googleapiclient.discovery import build
from google.oauth2 import service_account

# If modifying these scopes, delete the file data/token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# The ID and range of a sample spreadsheet.
FOUNTAIN_SPREADSHEET_ID = '1VR4EIkpohArT0LZk-0_JI_BVsMeIuxAyAkNTEwSNN8I'
FOUNTAIN_RANGE_NAME = 'Form Responses 1!A2:I'
WEBHOOK_URL = os.environ['WEBHOOK_URL']

# Address: tz1NAaEqTBd5WLLZjeGXrLMoxxxGy3tCUTQg
key = Key.from_encoded_key(
    os.environ['TEIA_FOUNTAIN_KEY'], os.environ['TEIA_FOUNTAIN_PASS'])
pytezos = pytezos.using(shell=os.environ['TEIA_RPC_NODE'], key=key)
acct_id = pytezos.key.public_key_hash()
acct = pytezos.account()

send_amt = os.environ['TEIA_AMOUNT']
send_to = []
applied = {}
retry_seconds = int(os.environ['INTERVAL'])
state_file = "data/statefile.json"

state = {"filled_rows": 0, "sent_message": False}
try:
    with open(state_file, "r") as f:
        state = json.load(f)
except FileNotFoundError:
    with open(state_file, "w") as f:
        json.dump(state, f)


def msg(msg):
    webhook = DiscordWebhook(url=WEBHOOK_URL, content=msg)
    webhook.execute()


def balance(acct_id):
    try:
        acct = pytezos.account(acct_id)
    except RpcError as e:
        print(e)
        return -1
    return int(acct['balance'])


def transfer(send_to, send_amt):
    opg = pytezos.transaction(destination=send_to, amount=Decimal(send_amt))
    res = run_opg(opg)
    while res == None:
        time.sleep(.1)
        return transfer(send_to, send_amt)

    op_hash = res['hash']
    while True:
        time.sleep(30)
        ver = verify_op(op_hash)
        if ver == 1:
            applied[send_to] = op_hash
            break
        elif ver == -1:
            print("Retry failed %s XTZ to %s" % (send_amt, send_to))
            return transfer(send_to, send_amt)
        else:
            print("Waiting for confirmation for %s" % op_hash)
            print(pytezos.shell.head.level())
            # ver 0 pass through and try again

    return op_hash

# 1 - verified
# 0 - not found
# -1 - failure


def verify_op(op_hash):
    try:
        # look 5 blocks back for our operation
        opg = pytezos.shell.blocks[-5:].find_operation(op_hash)
    except StopIteration as e:
        return 0
    ret = -1
    for op in OperationResult.iter_contents(opg):
        print(op['metadata']['operation_result']['status'])
        if op['metadata']['operation_result']['status'] == 'applied':
            ret = 1
            break
    return ret


def run_opg(opg):
    try:
        res = opg.autofill().sign().inject()
        return res
    except RpcError as e:
        retry = True
        for arg in e.args:
            if isinstance(arg, str):
                print("ERROR! %s" % arg)
            elif arg['kind'] != 'temporary':
                retry = False
                print("ERROR! %s" % arg)
                break
        if retry:
            return None
    except KeyError as ke:
        return None


def store_balance(service, row_num, balance):
    processed = '' if balance == 0 else 'Skipped'
    if balance == -1:
        processed = "Invalid Tezos account number"
    values = [
        [float(balance) / 1000000, processed]
    ]
    body = {'values': values}
    range_name = 'Form Responses 1!F%s:G%s' % (row_num, row_num)
    # print(range_name)
    result = service.spreadsheets().values().update(
        spreadsheetId=FOUNTAIN_SPREADSHEET_ID, range=range_name,
        valueInputOption='USER_ENTERED', body=body).execute()
    print('{0} cells updated.'.format(result.get('updatedCells')))


def store_results(service, row_num, op_hash):
    values = [
        [str(datetime.datetime.now()), "https://tzkt.io/%s" % op_hash]
    ]
    body = {'values': values}
    range_name = 'Form Responses 1!G%s:H%s' % (row_num, row_num)
    # print(range_name)
    result = service.spreadsheets().values().update(
        spreadsheetId=FOUNTAIN_SPREADSHEET_ID, range=range_name,
        valueInputOption='USER_ENTERED', body=body).execute()
    print('{0} cells updated.'.format(result.get('updatedCells')))


def save_state(state):
    with open(state_file, "w") as f:
        json.dump(state, f)


def bot_has_enough_balance(bot_balance, send_amt):
    if float(bot_balance / 1000000) < float(send_amt):
        if not state.get('sent_message'):
            state['sent_message'] = True
            print("bot balance too low %0.4f XTZ" % (bot_balance / 1000000))
            msg("Bot balance too low: %0.4f XTZ" % (bot_balance / 1000000))
        return False
    state['sent_message'] = False
    return True


def main():
    creds = None
    # The file data/token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('credentials.json'):
        creds = service_account.Credentials.from_service_account_file(
            'credentials.json', scopes=SCOPES)

    bot_balance = balance(acct_id)
    msg('Bot started, running with %s seconds interval. Current balance: %s XTZ' % (
        retry_seconds, bot_balance / 1000000))

    while True:
        bot_balance = balance(acct_id)

        # Call the Sheets API
        service = build('sheets', 'v4', credentials=creds)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=FOUNTAIN_SPREADSHEET_ID,
                                    range=FOUNTAIN_RANGE_NAME).execute()
        values = result.get('values', [])

        if bot_has_enough_balance(bot_balance, send_amt):
            if not values:
                print('No data found.')
            else:
                row_num = 1
                for row in values:
                    row_num += 1
                    if row and row[0].strip():
                        address = row[2].strip()
                        approved = row[4] == 'TRUE'
                        processed_on = row[6] if len(row) > 6 else ''
                        link = row[3].strip()
                        # print('%s, %s' % (address, approved))
                        if approved and processed_on == '':
                            acct_balance = balance(address)
                            # TODO - write balance to sheet
                            store_balance(service, row_num, acct_balance)
                            if acct_balance == 0:
                                op_hash = transfer(address, send_amt)
                                print('Sent %s to %s with %s' %
                                      (send_amt, address, op_hash))
                                msg('Sent %s to %s details: <https://tzkt.io/%s>' %
                                    (send_amt, address, op_hash))
                                store_results(service, row_num, op_hash)
                            else:
                                msg('Did not send %s to %s, already has %s XTZ' %
                                    (send_amt, address, acct_balance / 1000000))
                        else:
                            if row_num > state.get('filled_rows') + 1:
                                msg('New entry on the form: `%s`. Proof link: <%s>' % (address, link))
                                state['filled_rows'] += 1
        save_state(state)
        time.sleep(retry_seconds)


if __name__ == '__main__':
    main()

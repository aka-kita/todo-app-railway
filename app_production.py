import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Google Sheets API設定
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID', '1KgWUf0E2V_H-9dn-C7PIHnnnWR3HoTmbG93KRuCJpz0')

def get_credentials():
    """環境変数から認証情報を取得"""
    credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
    if credentials_json:
        return json.loads(credentials_json)
    return None

def save_credentials_to_file(credentials_dict):
    """認証情報を一時ファイルに保存"""
    with open('temp_credentials.json', 'w') as f:
        json.dump(credentials_dict, f)
    return 'temp_credentials.json'

class TodoManager:
    def __init__(self):
        self.service = None
        self.credentials = None
    
    def authenticate(self):
        """Google Sheets APIの認証を行う"""
        if os.path.exists('token.json'):
            self.credentials = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
            else:
                # 環境変数から認証情報を取得
                credentials_dict = get_credentials()
                if credentials_dict:
                    credentials_file = save_credentials_to_file(credentials_dict)
                    flow = Flow.from_client_secrets_file(credentials_file, SCOPES)
                    flow.redirect_uri = url_for('oauth2callback', _external=True)
                    authorization_url, state = flow.authorization_url(
                        access_type='offline',
                        include_granted_scopes='true'
                    )
                    # 一時ファイルを削除
                    if os.path.exists(credentials_file):
                        os.remove(credentials_file)
                    return authorization_url
                else:
                    # 本番環境では認証情報が必要
                    flash('認証情報が設定されていません。管理者にお問い合わせください。', 'error')
                    return None
        
        self.service = build('sheets', 'v4', credentials=self.credentials)
        return None
    
    def get_todos(self):
        """スプレッドシートからTodoリストを取得する"""
        if not self.service:
            return []
        
        try:
            range_name = 'A:D'  # A列: ID, B列: タイトル, C列: 内容, D列: 期日
            result = self.service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range=range_name
            ).execute()
            values = result.get('values', [])
            
            todos = []
            for i, row in enumerate(values[1:], start=2):  # ヘッダー行をスキップ
                if len(row) >= 4:
                    todos.append({
                        'id': i,
                        'title': row[1],
                        'content': row[2],
                        'due_date': row[3]
                    })
            return todos
        except Exception as e:
            print(f"Error getting todos: {e}")
            return []
    
    def add_todo(self, title, content, due_date):
        """新しいTodoをスプレッドシートに追加する"""
        if not self.service:
            return False
        
        try:
            # 新しい行のIDを取得
            todos = self.get_todos()
            new_id = len(todos) + 2  # ヘッダー行 + 既存のTodo数 + 1
            
            values = [[new_id, title, content, due_date]]
            body = {'values': values}
            
            range_name = f'A{new_id}:D{new_id}'
            self.service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            return True
        except Exception as e:
            print(f"Error adding todo: {e}")
            return False
    
    def update_todo(self, todo_id, title, content, due_date):
        """既存のTodoを更新する"""
        if not self.service:
            return False
        
        try:
            values = [[todo_id, title, content, due_date]]
            body = {'values': values}
            
            range_name = f'A{todo_id}:D{todo_id}'
            self.service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            return True
        except Exception as e:
            print(f"Error updating todo: {e}")
            return False
    
    def delete_todo(self, todo_id):
        """Todoを削除する"""
        if not self.service:
            return False
        
        try:
            # 行を削除
            request_body = {
                'requests': [{
                    'deleteDimension': {
                        'range': {
                            'sheetId': 0,
                            'discension': 'ROWS',
                            'startIndex': todo_id - 1,
                            'endIndex': todo_id
                        }
                    }
                }]
            }
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=SPREADSHEET_ID,
                body=request_body
            ).execute()
            return True
.* except Exception as e:
            print(f"Error deleting todo: {e}")
            return False

# グローバルTodoManagerインスタンス
todo_manager = TodoManager()

@app.route('/')
def index():
    """Todoリストの一覧表示"""
    auth_url = todo_manager.authenticate()
    if auth_url:
        return redirect(auth_url)
    
    todos = todo_manager.get_todos()
    return render_template('index.html', todos=todos)

@app.route('/oauth2callback')
def oauth2callback():
    """OAuth2認証のコールバック"""
    credentials_dict = get_credentials()
    if credentials_dict:
        credentials_file = save_credentials_to_file(credentials_dict)
        flow = Flow.from_client_secrets_file(credentials_file, SCOPES)
        flow.redirect_uri = url_for('oauth2callback', _external=True)
        
        authorization_response = request.url
        flow.fetch_token(authorization_response=authorization_response)
        
        credentials = flow.credentials
        with open('token.json', 'w') as token:
            token.write(credentials.to_json())
        
        # 一時ファイルを削除
        if os.path.exists(credentials_file):
            os.remove(credentials_file)
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        due_date = request.form['due_date']
        
        if todo_manager.add_todo(title, content, due_date):
            flash('Todoが正常に追加されました！', 'success')
        else:
            flash('Todoの追加に失敗しました。', 'error')
        
        return redirect(url_for('index'))
    
    return render_template('add_todo.html')

@app.route('/edit/<int:todo_id>', methods=['GET', 'POST'])
def edit_todo(todo_id):
    """既存のTodoを編集"""
    todos = todo_manager.get_todos()
    todo = next((t for t in todos if t['id'] == todo_id), None)
    
    if not todo:
        flash('Todoが見つかりません。', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        due_date = request.form['due_date']
        
        if todo_manager.update_todo(todo_id, title, content, due_date):
            flash('Todoが正常に更新されました！', 'success')
        else:
            flash('Todoの更新に失敗しました。', 'error')
        
        return redirect(url_for('index'))
    
    return render_template('edit_todo.html', todo=todo)

@app.route('/delete/<int:todo_id>')
def delete_todo(todo_id):
    """Todoを削除"""
    if todo_manager.delete_todo(todo_id):
        flash('Todoが正常に削除されました！', 'success')
    else:
        flash('Todoの削除に失敗しました。', 'error')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    # 本番環境ではdebug=Falseに設定
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

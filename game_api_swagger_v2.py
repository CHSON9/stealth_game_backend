from flask import Flask, request, jsonify
import mysql.connector
from flask import Blueprint

current_session_id = None


# DB 연결 설정 함수
def get_db_connection():
    connection = mysql.connector.connect(
        host='127.0.0.1',       
        user='root',            
        password='mysql1234', 
        database='tracer_db',
        buffered=True   
    )
    if not connection.is_connected():
        connection.reconnect(attempts=3, delay=1)
    return connection

# Blueprint 생성
api_bp = Blueprint('game_api', __name__)

#swagger_api 설정
#인증 및 사용자 관리 (REST)
#회원가입
@api_bp.route('/auth/signup', methods=['POST'])
def signup():
    """
    팀 회원가입 API
    ---
    tags:
      - Authentication
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: Signup
          properties:
            team_id:
              type: string
              example: "team_alpha"
            password:
              type: string
              example: "password123"
    responses:
      201:
        description: 팀 회원가입 성공
      400:
        description: 가입 실패 (중복된 팀 아이디 등)
    """
    data = request.json
    db = get_db_connection()
    cursor = db.cursor()
    try:
        sql = "INSERT INTO users (team_id, password, is_active) VALUES (%s, %s, 0)"
        cursor.execute(sql, (data.get('team_id'), data.get('password')))
        db.commit()
        return jsonify({"status": "success"}), 201
    except mysql.connector.Error as err:
        if err.errno == 1062:
            return jsonify({"status": "error", "message": "이미 사용 중인 팀 아이디입니다."}), 400
        return jsonify({"status": "error", "message": str(err)}), 400
    finally:
        cursor.close()
        db.close()

# 아이디 중복 확인
@api_bp.route('/auth/check-id', methods=['POST'])
def check_id():
    """
    팀 아이디 중복 확인 API
    ---
    tags:
      - Authentication
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id : CheckID
          properties:
            team_id:
              type: string
              description: 중복 확인할 팀 아이디
    responses:
      200:
        description: 사용 가능 여부 반환
    """
    data = request.json
    team_id = data.get('team_id')
    db = get_db_connection()
    cursor = db.cursor()
    try:
        sql = "SELECT COUNT(*) FROM users WHERE team_id = %s"
        cursor.execute(sql, (team_id,))
        count = cursor.fetchone()[0]
        if count > 0:
            return jsonify({"status": "exists", "message": "이미 사용 중인 팀 아이디입니다."}), 200
        return jsonify({"status": "success", "message": "사용 가능한 팀 아이디입니다."}), 200
    finally:
        cursor.close()
        db.close()


#로그인
@api_bp.route('/auth/login', methods=['POST'])
def login():
    """
    팀 로그인 API
    ---
    tags:
      - Authentication
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: Login
          properties:
            team_id:
              type: string
            password:
              type: string
    responses:
      200:
        description: 로그인 성공
    """
    data = request.json
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        sql = "SELECT * FROM users WHERE team_id = %s AND password = %s"
        cursor.execute(sql, (data.get('team_id'), data.get('password')))
        user = cursor.fetchone()
        if user:
            cursor.execute("UPDATE users SET is_active = 0 WHERE is_active = 1")
            update_sql = "UPDATE users SET is_active = 1 WHERE user_id = %s"
            cursor.execute(update_sql, (user['user_id'],))
            db.commit()

            print(f"[서버 로그] 팀 {user['team_id']}(ID: {user['user_id']}) 접속 - 세션 활성화")
            return jsonify({"status": "success", "user_id": user['user_id'], "team_id": user['team_id']})
        return jsonify({"status": "error", "message": "아이디 또는 비밀번호가 틀렸습니다."}), 401
    finally:
        cursor.close()
        db.close()


# 게임 세션 및 시작 (REST)
@api_bp.route('/game/start', methods=['POST'])
def game_start():
    """
    팀 단위 게임 세션 생성 및 초기화
    ---
    tags:
      - Game
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: GameStartRequest
          properties:
            user_id:
              type: integer
              description: 로그인 성공 후 보유한 고유 user_id (팀 식별 번호)
              example: 1
    responses:
      200:
        description: 세션 생성 성공
    """
    global current_session_id
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True) 
    
    try:
        cursor.execute("SELECT user_id FROM users WHERE is_active = 1 LIMIT 1")
        active_user = cursor.fetchone()
        
        if not active_user:
            return jsonify({"status": "error", "message": "현재 활성화된 로그인 세션(팀)이 없습니다."}), 400
            
        user_id = active_user['user_id']
        cursor.close() 
        
        cursor = db.cursor()
        sql = "INSERT INTO game_sessions (user_id, tagger_id, started_at) VALUES (%s, 0, NOW())"
        cursor.execute(sql, (user_id,))
        current_session_id = cursor.lastrowid 

        from app.api.shared_state import game as algorithm_game
        algorithm_game.current_session_id = current_session_id
        algorithm_game.score = 0
        algorithm_game.tagger_id = None  
        algorithm_game.phase = "playing"
        if hasattr(algorithm_game, 'start_game'):
            algorithm_game.start_game()

        db.commit()
        
        print(f"[서버 로그] 🎮 멀티/단일 하이브리드 게임 기동 - 세션 생성 성공 (User ID: {user_id}, Session ID: {current_session_id})")
        return jsonify({
            "status": "success", 
            "session_id": current_session_id,
            "user_id": user_id
        })
    except Exception as e:
        print(f"Game Start Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        cursor.close()
        db.close()


#게임 종료 및 결과 조회 (REST)
@api_bp.route('/game/end', methods=['POST'])
def game_end():
    """
    팀 최종 게임 결과 데이터 저장
    ---
    tags:
      - Game
    parameters:
      - name: body
        in: body
        required: false
        schema:
          properties:
            # 시연 편의성을 위해 아무것도 안 보내도 백엔드가 자동 매칭합니다.
    responses: 
      200:
        description: 저장 및 정산 완료
    """

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT user_id FROM users WHERE is_active = 1 LIMIT 1")
        active_user = cursor.fetchone()
        if not active_user:
            return jsonify({"status": "error", "message": "현재 활성화된 팀이 없습니다."}), 400
        user_id = active_user['user_id']

        cursor.execute("""
            SELECT session_id FROM game_sessions 
            WHERE user_id = %s AND ended_at IS NULL 
            ORDER BY started_at DESC LIMIT 1
        """, (user_id,))
        active_session = cursor.fetchone()
        if not active_session:
            return jsonify({"status": "error", "message": "마감할 활성화 세션을 찾을 수 없습니다."}), 400
        session_id = active_session['session_id']


        cursor.close()
        cursor = db.cursor() 

        from app.api.shared_state import game as algorithm_game
        touch_score = algorithm_game.score

        sql = """
            INSERT INTO game_results (session_id, user_id, touch_count, final_score) 
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(sql, (session_id, user_id, touch_score, touch_score))
        
        session_update_sql = "UPDATE game_sessions SET ended_at = NOW() WHERE session_id = %s"
        cursor.execute(session_update_sql, (session_id,))

        algorithm_game.phase = "idle"  
        
        if hasattr(algorithm_game, 'end_game'):
            algorithm_game.end_game()
            
        db.commit()

        print(f"[서버 로그] 🏁 세션 자동 마감 성공! (Session: {session_id}, User: {user_id}, Score: {touch_score})")

        return jsonify({
            "status": "success",
            "session_id": session_id,
            "touch_count": touch_score,
            "final_score": touch_score
        }), 200
    
    except Exception as e: 
        print(f"Game End Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        cursor.close()
        db.close()

# 5. 결과 상세 조회 
@api_bp.route('/game/result/<int:session_id>', methods=['GET'])
def get_game_result(session_id):
    """
    결과창용 팀 상세 성적 데이터 조회
    ---
    tags:
      - Game
    parameters:
      - name: session_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: 조회 성공
    """
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        sql = "SELECT * FROM game_results WHERE session_id = %s"
        cursor.execute(sql, (session_id,))
        results = cursor.fetchall()
        return jsonify({"status": "success", "data": results})
    finally:
        cursor.close()
        db.close()



# # 마이페이지 데이터 조회 API - 팀명 입력하지 않음
@api_bp.route('/team/my/game-records', methods=['GET'])
def get_game_records():
    """
    마이페이지 화면용 통합 데이터 조회 API
    ---
    tags:
      - MyPage
    description: |
      마이페이지 진입 시 호출하는 통합 API입니다. 
      2가지 패키지를 제공합니다:
      
      1. `my_last_record`: 현재 로그인한 팀의 가장 최근 게임 결과 1개 
      2. `top_records`: 팀에 관계없이 전체 데이터 중 터치 횟수(tag_count)가 가장 높은 역대 상위 기록 리스트 
    responses:
      200:
        description: 마이페이지에 필요한 모든 데이터를 성공적으로 반환합니다.
        schema:
          properties:
            status:
              type: string
              example: "success"
            data:
              type: object
              properties:
                my_team_id:
                  type: string
                  example: "team_alpha"
                my_last_record:
                  type: object
                  description: 우리 팀의 가장 최근 플레이 기록 (없으면 null)
                  properties:
                    record_id:
                      type: integer
                    date:
                      type: string
                    time:
                      type: string
                    duration:
                      type: string
                    tag_count:
                      type: integer
                top_records:
                  type: array
                  description: 역대 모든 팀 통틀어 높은 점수 순서로 정렬된 성적 리스트
                  items:
                    properties:
                      record_id:
                        type: integer
                      team_id:
                        type: string
                        description: 플레이한 팀의 고유 텍스트 ID
                      date:
                        type: string
                      time:
                        type: string
                      duration:
                        type: string
                      tag_count:
                        type: integer
"""

    db = get_db_connection()
    try:
        cursor = db.cursor(dictionary=True, buffered=True)
        
        active_user_sql = """
            SELECT s.user_id AS active_user_id, u.team_id AS active_team_string_id
            FROM game_sessions s
            JOIN users u ON s.user_id = u.user_id
            ORDER BY s.started_at DESC
            LIMIT 1
        """ 

        cursor.execute(active_user_sql)  
        session_data = cursor.fetchone()
        
        if not session_data:
            return jsonify({"status": "error", "message": "조회할 수 있는 최근 게임 세션 기록이 존재하지 않습니다."}), 444
            
        active_user_id = session_data['active_user_id']          
        active_team_string_id = session_data['active_team_string_id']  


        query_my_last = """
            SELECT 
                r.result_id AS record_id,
                DATE_FORMAT(s.started_at, '%Y-%m-%d') AS date,
                DATE_FORMAT(s.started_at, '%H:%i:%s') AS time,
                IFNULL(DATE_FORMAT(TIMEDIFF(s.ended_at, s.started_at), '%i:%s'), '00:00') AS duration,
                r.touch_count AS tag_count
            FROM game_results r
            JOIN game_sessions s ON r.session_id = s.session_id
            WHERE r.user_id = (SELECT s2.user_id FROM game_sessions s2 ORDER BY s2.started_at DESC LIMIT 1)
            ORDER BY s.started_at DESC
            LIMIT 1
        """
        cursor.execute(query_my_last)
        my_last_record = cursor.fetchone()


        cursor.close()
        cursor = db.cursor(dictionary=True, buffered=True)

        query_top9 = """
            SELECT 
                r.result_id AS record_id,
                u.team_id AS team_id,
                DATE_FORMAT(s.started_at, '%Y-%m-%d') AS date,
                DATE_FORMAT(s.started_at, '%H:%i:%s') AS time,
                IFNULL(DATE_FORMAT(TIMEDIFF(s.ended_at, s.started_at), '%i:%s'), '00:00') AS duration,
                r.touch_count AS tag_count
            FROM game_results r
            JOIN game_sessions s ON r.session_id = s.session_id
            JOIN users u ON r.user_id = u.user_id
            ORDER BY r.touch_count DESC, s.started_at DESC
        """
        cursor.execute(query_top9)
        top_records = cursor.fetchall()
        
        cursor.close()


        return jsonify({
            "status": "success",
            "data": {
                "my_team_id": active_team_string_id,          
                "my_last_record": my_last_record if my_last_record else None,
                "top_records": top_records
            }
        }), 200

    except Exception as e:
        print(f"마이페이지 데이터 조회 에러: {e}")
        return jsonify({"status": "error", "message": f"서버 내부 에러: {str(e)}"}), 500
    finally:
        db.close()


@api_bp.route('/detect_test', methods=['POST'])
def detect_test_docs():
    """
    움직임 감지 로그 기록 (AI 엔진/테스트용)
    ---
    tags:
      - Game (Testing Only)
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            session_id:
              type: integer
              example: 1
    responses:
      200:
        description: 로그 기록 성공
    """
    return jsonify({"status": "success", "message": "이건 문서 전용입니다."}), 200

# 실시간 통신 (Socket.io) 소켓 명세서 
@api_bp.route('/socket_docs')
def socket_docs():
    """
    실시간 통신(Socket.io) 명세서 (멀티 카메라 하이브리드 대응 버전)
    ---
    tags:
      - Real-time (Socket.io)
    description: |
      이 섹션은 하이브리드 멀티캠 스텔스 비전 시스템의 모든 실시간 소켓 이벤트를 정의합니다.
      
      ### [1] 클라이언트 -> 서버 (Client -> Server Events)
      
      1. **`image_frame`**
         - **설명**: 프론트 웹앱에서 가져온 영상 프레임을 실시간으로 전송합니다.
         - **데이터 규격**: 
           ```json
           {
             "image": "data:image/jpeg;base64,.....(Base64 문자열)",
             "camera_id": "cam1" // 또는 "cam2" (★ 필수: 장치별 룸 분기 식별자)
           }
           ```
         - **멀티캠 구동 가이드**:
           - 1번 카메라 장치(노트북 기본 웹캠 등)는 `"camera_id": "cam1"`을 주입하여 송신합니다.
           - 2번 가상 카메라 장치(Camo 앱 연동 스마트폰 등)는 `"camera_id": "cam2"`를 주입하여 송신합니다.
           - 만약 테스트 과정에서 1대의 카메라만 인입될 경우, 서버는 자동으로 실시간 감지를 수행하여 해당 카메라의 단일 충돌 데이터만으로 점수를 산정하는 단일캠 모드로 하이브리드 자동 스위칭됩니다.
         
      2. **`request_random_tagger`** - **설명**: 프론트 UI의 '술래 지정' 버튼 클릭 시 초고속 소켓 파이프라인을 타고 화면 내 실시간 인물 중 무작위 술래 선정을 연산합니다.
         - **데이터 규격**: 없음 (또는 빈 객체 `{}`)
         
      3. **`game_pause`** - **설명**: 프론트 UI의 '일시정지' 버튼 클릭 시 실시간 AI 인페인팅 및 터치 연산 루프를 일시 고정합니다.
         
      4. **`game_resume`** - **설명**: 프론트 UI의 '다시시작' 버튼 클릭 시 멈춰있던 AI 연산 루프를 즉각 정상 재개합니다.
         
      ---
      
      ### [2] 서버 -> 클라이언트 (Server -> Client Events)
      
      1. **`game_update`** - **설명**: AI 엔진의 가공물(스텔스 필터링 완료 프레임)과 게임 데이터 스코어를 실시간으로 브로드캐스트합니다.
         - **데이터 구조 예시**:
           ```json
           {
             "status": "playing", 
             "result_image": "data:image/jpeg;base64,.....", // 스텔스 투명화 가공이 완료된 단일 렌더링 화면
             "score": 14,
             "tagger_id": 2,
             "invisible_ids": [1, 3]
           }
           ```
         - **화면 렌더링 가이드**: `result_image`는 기본적으로 `cam1`의 결과 화면을 대표로 송출하여 프론트엔드의 트래픽 부하를 줄입니다. 다만, `cam1` 신호가 끊어지고 `cam2`만 작동하는 단일캠 테스트 환경일 경우 서버가 똑똑하게 `cam2` 가공 화면으로 자동 스위칭하여 보냅니다. 프론트엔드는 이 들어오는 하나의 이미지 스트링만 받아 화면에 그려주면 끝납니다.
    """
    return "이 페이지는 Swagger 문서용입니다."

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import base64
import mysql.connector
import cv2
import numpy as np
import os
from flasgger import Swagger
from game_api_swagger_v2 import api_bp
import game_api_swagger_v2 as api_meta
import random
from flask import Response # 추후 삭제


# AI 알고리즘 파일 임포트
try:
    from app.cv.yolo_inpaint_stealth import YoloInpaintStealth
    from app.tracking.simple_tracker import SimpleTracker
    
    from app.api.shared_state import game as game_manager
    from app.api.shared_state import multi_camera
    print("AI 모듈 및 싱글톤 shared_state 로드 성공")
except ImportError as e:
    print(f"모듈 임포트 에러: {e}")
    print("현재 디렉토리 구성이 올바른지 확인하세요.")

print("AI 엔진 초기화 중... 잠시만 기다려주세요.")
stealth_engine1 = YoloInpaintStealth()
stealth_engine2 = YoloInpaintStealth()

tracker1 = SimpleTracker()
tracker2 = SimpleTracker()
print("멀티 카메라 AI 엔진 초기화 완료!")

app = Flask(__name__)
CORS(app)
app.register_blueprint(api_bp)
swagger = Swagger(app)  
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent_uwsgi' if os.environ.get('USE_GEVENT') else 'threading')


# Base64를 OpenCV 이미지로 변환하는 함수
def base64_to_image(base64_string):
    try:
        if not base64_string or ';base64,' not in base64_string:
            return None
        format, imgstr = base64_string.split(';base64,') 
        img_data = base64.b64decode(imgstr)
        nparr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return frame
    except Exception as e:
        print(f"이미지 변환 에러: {e}")
        return None


# MySQL 연결 설정 함수
def get_db_connection():
    connection =  mysql.connector.connect(
        host='127.0.0.1',
        user='root',         
        password='mysql1234', 
        database='tracer_db',
        get_warnings=True,
        raise_on_warnings=True,
        connection_timeout=5
    )
    if not connection.is_connected():
        connection.reconnect(attempts=3, delay=1)
    return connection

@app.route('/')
def home():
    return "AI 실시간 게임 서버 및 데이터베이스가 가동 중입니다."

# 데이터 수신 및 처리 라우트
@app.route('/detect', methods=['POST'])
def detect():
    data = request.json
    print(f"\n[서버 로그] /detect 호출됨: {data}") 
    
    if not data:
        return jsonify({"status": "fail", "message": "데이터가 없습니다."}), 400
    
    session_id = data.get('session_id') or game_manager.current_session_id
    print(f"[서버 로그] 기록할 세션 ID: {session_id}")

    if not session_id:
        return jsonify({"status": "fail", "message": "활성화된 세션 ID를 찾을 수 없습니다."}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        sql = "INSERT INTO motion_logs (session_id, timestamp) VALUES (%s, NOW())"
        cursor.execute(sql, (session_id,))
        conn.commit() 
        
        print("[서버 로그] DB 저장 완료!")
        
        cursor.close()
        conn.close()
        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"[서버 로그] DB 저장 에러: {e}")
        return jsonify({"status": "fail", "error": str(e)}), 500
    
# 가공 영상 링크로 보기 - 함수
def generate_video_stream():
    import time
    while True:
        base64_data = getattr(game_manager, 'latest_frame_base64', None)
        
        if base64_data and ';base64,' in base64_data:
            try:
                _, imgstr = base64_data.split(';base64,')
                img_bytes = base64.b64decode(imgstr)
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + img_bytes + b'\r\n')
            except Exception:
                pass
        
        time.sleep(0.03)

# 가공 영상 링크로 보기 - 소켓
@app.route('/video_feed')
def video_feed():
    """
    알고리즘 담당자용 실시간 AI 가공 화면 모니터링 스트리밍 스트림
    """
    return Response(
        generate_video_stream(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

#프론트엔드에서 서버 연결 성공했는지 확인용
@socketio.on('connect')
def handle_connect():
    """
    프론트엔드 브라우저가 백엔드 서버에 실시간 소켓 연결을 성공했을 때 실행됨
    """
    print(f"\n" + "="*50)
    print(f"[소켓 로그] 🎉 프론트엔드 브라우저 접속 성공! 🎉")
    print(f"  - 연결된 소켓 ID: {request.sid}")
    print(f"  - 접속 기기 정보: {request.headers.get('User-Agent')}")
    print("="*50 + "\n")

#영상 가공
@socketio.on('image_frame')
def handle_stealth_game(data):
    
    if not data :
        return
    
    if getattr(game_manager, 'phase', 'idle') == 'paused':
        return
    
    if not getattr(game_manager, 'current_session_id', None):
        try:
            db = get_db_connection()
            cursor = db.cursor()
            cursor.execute("SELECT session_id FROM game_sessions ORDER BY started_at DESC LIMIT 1")
            result = cursor.fetchone()
            if result:
                game_manager.current_session_id = result[0]
                print(f"[자동 동기화] 비어있던 session_id를 {result[0]}번으로 채웠습니다.")
            cursor.close()
            db.close()
        except Exception as e:
            print(f"세션 ID 자동 조회 실패: {e}")
        finally:
            if cursor: cursor.close()
            if db: db.close()
        
    img_base64 = data.get('image')
    camera_id = data.get('camera_id', 'cam1')  
    frame = base64_to_image(img_base64)

    if frame is None:
        return

    try:
        frame = cv2.resize(frame, (640, 360))

        if camera_id == 'cam1':
            detections = stealth_engine1.detect(frame)
            if detections is None: detections = []
            tracks = tracker1.update(detections, frame)
            game_manager.update(tracks)
        else:
            detections = stealth_engine2.detect(frame)
            if detections is None: detections = []
            tracks = tracker2.update(detections, frame)
            if not is_cam1_alive:
                game_manager.update(tracks)

        collision_detected, target_user_id = game_manager.detect_collision(tracks)

        multi_camera.update_camera(
            camera_id,
            tracks,
            collision_detected,
            target_user_id
        )

        import time
        current_time = time.time()
        
        is_cam1_alive = (current_time - multi_camera.cam_states["cam1"]["timestamp"]) < 3.0
        is_cam2_alive = (current_time - multi_camera.cam_states["cam2"]["timestamp"]) < 3.0

        if is_cam1_alive and is_cam2_alive:
            valid_tag, final_caught_id = multi_camera.is_valid_tag()
            mode_label = "실전 멀티캠 모드 (2대 동시 교차 인증)"
        else:
            valid_tag = collision_detected
            final_caught_id = target_user_id
            mode_label = f"임시 단일캠 테스트 모드 (활성화 카메라: {camera_id})"

        if game_manager.phase == "playing" and valid_tag:
            game_manager.apply_valid_tag(final_caught_id)

        if game_manager.phase == "playing":
            if camera_id == 'cam1':
                result_frame, mask = stealth_engine1.process(frame, tracks)
            else:
                result_frame, mask = stealth_engine2.process(frame, tracks)
                
        else:
            result_frame = frame.copy()
            
            for track in tracks:
                try:
                    if isinstance(track, dict):
                        bbox = track.get('bbox', [0, 0, 0, 0])
                        x1, y1, x2, y2 = map(int, bbox)
                        track_id = track.get('track_id', 0)
                    else:
                        if not track.is_confirmed() or track.time_since_update > 1:
                            continue
                        bbox = track.to_tlbr()
                        x1, y1, x2, y2 = map(int, bbox)
                        track_id = track.track_id
                    

                    # # ID만 그리기
                    # cv2.rectangle(result_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    # cv2.putText(result_frame, f"ID: {track_id+1}", (x1, y1 - 10), 
                    #             cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                    
                    # #TAGGER도 그리기
                    # if game_manager.tagger_id is not None and track_id == game_manager.tagger_id:
                    #     color = (0, 0, 255)  
                    #     label = f"TAGGER {track_id + 1}"
                    # else:
                    #     color = (0, 255, 0)  
                    #     label = f"RUNNER {track_id + 1}"
                    
                    # cv2.rectangle(result_frame, (x1, y1), (x2, y2), color, 2)
                    # cv2.putText(result_frame, label, (x1, y1 - 10), 
                    #             cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                    #위에 두 방식 합침
                    if game_manager.tagger_id is not None and track_id == game_manager.tagger_id:
                        color = (0, 0, 255)  
                        label = f"TAGGER : ID {track_id + 1}"
                    
                    else:
                        color = (0, 255, 0)  
                        label = f"RUNNER : ID {track_id + 1}"
                    
                    cv2.rectangle(result_frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(result_frame, label, (x1, y1 - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    
                except Exception as track_err:
                    print(f"[디버그 로그] 개별 트랙 드로잉 건너뜀: {track_err}")

        # 실시간 점수/시간/상태 텍스트를 화면 캔버스에 표시
        cv2.putText(result_frame, f"Score: {game_manager.score}", (20, 40), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # if hasattr(game_manager, 'get_time_left'):
        #     cv2.putText(result_frame, f"Time: {int(game_manager.get_time_left())}", (20, 80), 
        #                 cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # if game_manager.phase == "paused":
        #     cv2.putText(result_frame, "PAUSED", (180, 180), 
        #                 cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 255), 4)

        # if getattr(game_manager, 'finished', False) or game_manager.phase == "finished":
        #     cv2.putText(result_frame, "GAME OVER", (120, 180), 
        #                 cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 4)

        print(f"[실시간 디버그] 상태: {game_manager.phase} | 수신: {camera_id} | 트랙수: {len(tracks)} | 충돌여부: {collision_detected} | 최종점수: {game_manager.score}")

        if camera_id == 'cam1' or (not is_cam1_alive and camera_id == 'cam2'):
            _, buffer = cv2.imencode('.jpg', result_frame)
            result_base64 = base64.b64encode(buffer).decode('utf-8')
            game_manager.latest_frame_base64 = f"data:image/jpeg;base64,{result_base64}"

        emit('game_update', {
            "score": game_manager.score,
            "tagger_id": game_manager.tagger_id,
            "invisible_ids": [int(x) for x in list(game_manager.get_invisible_ids() if hasattr(game_manager, 'get_invisible_ids') else [])],
            "status": game_manager.phase, 
            "result_image": getattr(game_manager, 'latest_frame_base64', None)
        }, broadcast=True)

    except cv2.error as e:
        print(f"OpenCV 처리 에러 (프레임 건너뜀): {e}")
    except Exception as e:
        print(f"예상치 못한 실시간 처리 에러: {e}")


# 🎯 UI '술래 지정' 버튼 클릭 시 실시간 초고속 소켓 랜덤 배정 
@socketio.on('request_random_tagger')
def handle_request_random_tagger(data):
    print(f"[소켓 수신] 술래 지정 요청 핸들러 가동 (데이터: {data})")
    try:
        game_manager.select_tagger_from_current_tracks()  
        
        chosen_tagger = game_manager.tagger_id  
        
        if chosen_tagger is not None:
            print(f"\n[초고속 소켓 엔진] 🎲 실시간 랜덤 술래 배정 성공! -> Track ID: {chosen_tagger}\n")
            
            if game_manager.current_session_id:
                db = get_db_connection()
                cursor = db.cursor()
                cursor.execute(
                    "UPDATE game_sessions SET tagger_id = %s WHERE session_id = %s",
                    (chosen_tagger, game_manager.current_session_id)
                )
                db.commit()
                cursor.close()
                db.close()
                print("[데이터베이스] 세션 테이블 술래 정보 업데이트 완료!")
                
            emit('game_update', {
                "status": game_manager.phase,  
                "result_image": getattr(game_manager, 'latest_frame_base64', None), 
                "score": game_manager.score,
                "tagger_id": game_manager.tagger_id,
                "invisible_ids": list(game_manager.get_invisible_ids() if hasattr(game_manager, 'get_invisible_ids') else [])
            }, broadcast=True)

        else:
            print("\n[🚨 소켓 엔진 경고] 현재 카메라 화면에 인식된 플레이어가 아무도 없어 술래를 뽑지 못했습니다.\n")
            emit('game_update', {
                "status": game_manager.phase,
                "result_image": getattr(game_manager, 'latest_frame_base64', None),
                "score": game_manager.score,
                "tagger_id": None,
                "invisible_ids": []
            }, broadcast=True)

    except Exception as e:
        print(f"❌ 술래 지정 소켓 처리 중 대형 에러 발생: {e}")


# ⏸️ UI '일시정지' 버튼 클릭 시 연산 상태 제어 플래그 ON
@socketio.on('game_pause')
def handle_game_pause(data=None):
    game_manager.pause_game() 
    print(f"[소켓 엔진] 게임 일시정지 상태 돌입 (데이터: {data})")
    emit('game_update', {
        "status": game_manager.phase,
        "result_image": getattr(game_manager, 'latest_frame_base64', None),
        "score": game_manager.score,
        "tagger_id": game_manager.tagger_id,
        "invisible_ids": list(game_manager.get_invisible_ids() if hasattr(game_manager, 'get_invisible_ids') else [])
    }, broadcast=True)

# ▶️ UI '다시시작' 버튼 클릭 시 연산 상태 제어 플래그 OFF
@socketio.on('game_resume')
def handle_game_resume(data=None):
    game_manager.resume_game()  
    print(f"[소켓 엔진] 게임 재개 상태 돌입 (데이터: {data})")
    emit('game_update', {
        "status": game_manager.phase,
        "result_image": getattr(game_manager, 'latest_frame_base64', None),
        "score": game_manager.score,
        "tagger_id": game_manager.tagger_id,
        "invisible_ids": list(game_manager.get_invisible_ids() if hasattr(game_manager, 'get_invisible_ids') else [])
    }, broadcast=True)



#비정상 종료 -> 로그아웃 없이 브라우저 꺼버리기
@socketio.on('disconnect')
def handle_disconnect():
    """
    브라우저 종료 시 모든 유저의 활성화 상태를 초기화
    """
    print("\n[소켓 로그] 브라우저 연결 종료 감지 - 전체 유저 상태 초기화 시작")
    
    # db = get_db_connection()
    # cursor = db.cursor()
    # try:
    #     sql = "UPDATE users SET is_active = 0 WHERE is_active = 1"
    #     cursor.execute(sql)
    #     db.commit()
        
    #     print(f"[소켓 로그] 초기화 완료: 활성화된 팀 세션이 오프라인 처리됨")
    # except Exception as e:
    #     print(f"Disconnect Update Error: {e}")
    # finally:
    #     cursor.close()
    #     db.close()

# 서버 실행
if __name__ == '__main__':
    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("UPDATE users SET is_active = 0")
        db.commit()
        cursor.close()
        db.close()
        print("[부팅 로그] 서버가 시작되면서 기존 활성화된 팀들의 세션을 오프라인(0) 처리했습니다.")
    except Exception as e:
        print(f"[부팅 에러] 초기화 실패: {e}")

    print("\n" + "="*50)
    print("  서버가 성공적으로 실행되었습니다!")
    print("  - API 문서(Swagger): http://127.0.0.1:5000/apidocs")
    print("  - 실시간 서버 주소: http://127.0.0.1:5000")
    print("="*50 + "\n")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)



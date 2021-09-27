from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

from pymongo import MongoClient
from bson.objectid import ObjectId

from datetime import datetime

client = MongoClient('mongodb://test:test@13.124.151.213:27017')
db = client.ftime


@app.route('/', methods=['GET'])
def main_page():
    challenges = objectIdDecoder(list(db.challenge.find({})))
    return render_template('index.html', challenges=challenges)


@app.route('/error', methods=['GET'])
def error_page():
    return render_template('404.html')


@app.route('/user', methods=['GET'])
def user_detail_page():
    return render_template('user.html')


@app.route('/challenge/create', methods=['GET'])
def challenge_create_page():
    return render_template('challenge-create.html')


@app.route('/challenge/<challengeId>', methods=['GET'])
def challenge_detail_page(challengeId):
    challenge = db.challenge.find_one({'_id': ObjectId(challengeId)})
    challenge['_id'] = str(challenge['_id'])
    return render_template("challenge-detail.html", challenge=challenge)


# 준호님 code start


# 준호님 code end

# 수빈님 code start

# @app.route('/challenge', methods=['GET'])
# def get_challenge():
#     challenges = list(db.challenge.find({}))
#     json_str = dumps(challenges)
#     print(json_str)
#     return jsonify({'all_challenges': json_str})


@app.route('/challenge', methods=['POST'])
def save_challenge():
    title_receive = request.form["title_give"]
    decs_receive = request.form["desc_give"]
    period_receive = request.form["period_give"]

    file_len = len(request.files)
    # file_len 이 0이면 JS에서 파일을 안보낸준 것!
    # 파일을 안보내줬으면 default 파일이름을 넘겨준다.
    if file_len == 0:
        full_file_name = "default.png"  # default 파일이름 설정
    else:
        # 파일을 제대로 전달해줬으면 파일을 꺼내서 저장하고 파일이름을 넘겨준다.
        image_receive = request.files["image_give"]

        extension = image_receive.filename.split('.')[-1]
        today = datetime.now()
        mytime = today.strftime('%Y-%m-%d-%H-%M-%S')

        filename = f'file-{mytime}'

        save_to = f'static/assets/img/{filename}.{extension}'
        image_receive.save(save_to)

        full_file_name = f'{filename}.{extension}'

    doc = {
        'challenge_title': title_receive,
        'challenge_desc': decs_receive,
        'challenge_img': full_file_name,
        'challenge_startTime': period_receive.split(',')[0],
        'challenge_endTime': period_receive.split(',')[1],
        'challenge_host': 'admin'
    }

    db.challenge.insert_one(doc)
    return jsonify({'msg': "챌린지 등록 되었습니다."})


@app.route('/challenge/delete', methods=['POST'])
def delete_word():
    host_receive = request.form['host_give']
    db.challenge.delete_one({'challenge_host': host_receive})
    return jsonify({'result': 'success', 'msg': '챌린지 삭제 되었습니다.'})


# 수빈님 code end

# 현규님 code start
def objectIdDecoder(list):
    results = []
    for document in list:
        document['_id'] = str(document['_id'])
        results.append(document)
    return results


# 현규님 code end

if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)

import requests
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, make_response
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
import os
import jwt
import hashlib
from datetime import datetime, timedelta
import boto3
from apscheduler.schedulers.background import BackgroundScheduler
from decorator import login_required

application = Flask(__name__)
application.config['TEMPLATES_AUTO_RELOAD'] = True
cors = CORS(application, resources={r'/*': {'origins': '*'}})

# environment variable setting
load_dotenv()
# MongoDB setting
client = MongoClient(os.environ.get('MONGO_URL'))
db = client.ftime

SECRET_KEY = os.environ.get('SECRET_KEY')
TOKEN_NAME = 'fever-time'


@application.route('/', methods=['GET'])
def main_page():
    return render_template('index.html')


@application.route('/error', methods=['GET'])
def error_page():
    return render_template('404.html')


@application.route('/find', methods=['GET'])
def find_pw_page():
    return render_template('findPw.html')


@application.route('/challenge', methods=['GET'])
def challenge_create_page():
    return render_template('challenge-create.html')


@application.route('/sign_up', methods=['GET'])
def sign_up():
    return render_template('sign-up.html')


@application.route('/challenge/detail', methods=['GET'])
def challenge_detail_page():
    return render_template('challenge-detail.html')


@application.route('/login', methods=['GET'])
def login():
    return render_template('login.html')


@application.route('/search', methods=['GET'])
def search_challenge():
    search_receive = request.args['search']

    search_challenges = object_id_decoder(list(db.challenge.find({'challenge_title': {'$regex': search_receive}})))
    set_challenges_people(search_challenges)

    return jsonify({"challenges": search_challenges})


@application.route('/user', methods=['GET'])
@login_required
def user_page():
    kakao_login = True
    user_id = request.user_id
    if '@' in user_id:
        kakao_login = False

    join_challenge_id_list = list(db.join.distinct('join_challenge', {'join_user': user_id}))

    challenge_cnt = dict()
    challenge_cnt['ing'] = 0
    challenge_cnt['pause'] = 0
    challenge_cnt['end'] = 0

    challenges = []
    for challenge_id in join_challenge_id_list:
        challenge = db.challenge.find_one({'_id': ObjectId(challenge_id)})
        challenges.append(challenge)

        if challenge['challenge_status'] == 1:
            challenge_cnt['pause'] += 1
        elif challenge['challenge_status'] == 0:
            challenge_cnt['ing'] += 1
        else:
            challenge_cnt['end'] += 1

    user_info = db.users.find_one({'user_email': user_id}, {'_id': False})

    return render_template('user.html', user=user_info, challenges=challenges, challenge_cnt=challenge_cnt,
                           kakaoLogin=kakao_login)


@application.route('/user/name', methods=['POST'])
@login_required
def update_user_name():
    name_receive = request.form['name_give']
    user_id = request.user_id

    db.users.update_one({'user_email': user_id}, {'$set': {'user_name': name_receive}})
    db.join.update_many({'join_user': user_id}, {'$set': {'join_user_name': name_receive}})

    return jsonify({'msg': '?????? ?????? ??????!'})


@application.route('/challenge/<challenge_id>', methods=['GET'])
def get_challenge(challenge_id):
    challenge = db.challenge.find_one({'_id': ObjectId(challenge_id)})
    challenge['_id'] = str(challenge['_id'])

    # ????????? ?????? ????????????
    joins = list(db.join.find({'join_challenge': challenge_id}, {'_id': False}))

    # ????????? ???????????? ????????????
    if 'challenge_categories' in challenge:
        categories = ', '.join(challenge['challenge_categories']) \
            .replace('category1', '??????') \
            .replace('category2', '??????') \
            .replace('category3', '??????')
    else:
        categories = ''

    # ?????? ????????? ????????????(3???)
    related_challenge = object_id_decoder(list(db.challenge.find({'_id': {'$ne': ObjectId(challenge_id)}}).limit(3)))
    set_challenges_people(related_challenge)

    challenge['people'] = len(list(db.join.distinct('join_user', {'join_challenge': challenge_id})))
    join = list(db.join.distinct('join_user', {'join_challenge': challenge_id}))
    token_receive = request.cookies.get(TOKEN_NAME)

    status = False
    status_join = False

    try:
        payload = jwt.decode(token_receive, SECRET_KEY, algorithms=['HS256'])
        status = (challenge['challenge_host'] == payload['id'])  # ?????? ?????? ??????????????? True
        status_join = (payload['id'] in join)  # ????????? ?????? ?????? ??? ???????????? ????????? TRUE
    finally:
        return jsonify({'challenge': challenge, 'status': status, 'categories': categories,
                        'related_challenge': related_challenge, 'status_join': status_join, 'joins': joins})


@application.route('/sign_in', methods=['POST'])
def sign_in():
    # ?????????
    email_receive = request.form['user_email']
    password_receive = request.form['user_pw']

    pw_hash = hashlib.sha256(password_receive.encode('utf-8')).hexdigest()
    result = db.users.find_one({'user_email': email_receive, 'user_pw': pw_hash})
    if result is not None:
        return jsonify({'result': 'success', 'token': get_jwt_token(email_receive)})
    else:  # ?????? ?????????
        return jsonify({'result': 'fail', 'msg': '?????????/??????????????? ???????????? ????????????.'})


@application.route('/sign_up', methods=['POST'])
def sign_up_save():
    email_receive = request.form['user_email']
    username_receive = request.form['user_name']
    password_receive = request.form['user_pw']
    password_hash = hashlib.sha256(password_receive.encode('utf-8')).hexdigest()

    doc = {
        'user_email': email_receive,
        'user_name': username_receive,
        'user_pw': password_hash
    }

    db.users.insert_one(doc)

    return jsonify({'result': 'success', 'msg': '???????????? ???????????????.'})


@application.route('/sign_up/check_dup', methods=['POST'])
def check_dup():
    email_receive = request.form['user_email']

    exists = bool(db.users.find_one({'user_email': email_receive}))

    return jsonify({'result': 'success', 'exists': exists})


@application.route('/check_pwd', methods=['POST'])  # ?????? ??????????????? ????????? ??????
@login_required
def check_pwd():
    password_receive = request.form['pwd']
    pw_hash = hashlib.sha256(password_receive.encode('utf-8')).hexdigest()

    exists = bool(db.users.find_one({'user_email': request.user_id, 'user_pw': pw_hash}))

    return jsonify({'result': exists})


@application.route('/change_pwd', methods=['PUT'])  # ???????????? ??????
@login_required
def change_pwd():
    password_receive = request.args.get('pwd')
    pw_hash = hashlib.sha256(password_receive.encode('utf-8')).hexdigest()

    db.users.update_one({'user_email': request.user_id}, {'$set': {'user_pw': pw_hash}})

    return jsonify({'result': 'success'})


@application.route('/unregister', methods=['POST'])  # ????????????
@login_required
def unregister():
    user_id = request.user_id

    challenges = list(db.challenge.find({'challenge_host': user_id}))
    for challenge in challenges:
        challenge_id = str(challenge['_id'])
        delete_join_data(challenge_id)
        delete_challenge_date(challenge_id)

    db.users.delete_one({'user_email': user_id})  # ????????? ?????? ??????

    return jsonify({'result': 'success'})


@application.route('/oauth/callback', methods=['GET'])
def oauth():
    # code??? index.html??? ????????? ?????? url??? ?????? ??? ??? ????????????. ?????? url??? ???????????? ??????id, return uri??? ???????????? ????????????.
    # ????????? ???????????? ???????????? ????????? ??? ????????? ????????? ??????????????????.
    code = request.args.get('code')

    # ??? ????????? ????????? ????????? ????????? ???????????? ?????????. ????????? POST ????????? ?????? header??? body?????????.
    client_id = '568f2b791efeffd312f12ece9bb5faea'
    redirect_uri = 'https://fevertime.shop/oauth/callback'
    token_url = 'https://kauth.kakao.com/oauth/token'
    token_headers = {
        'Content-type': 'application/x-www-form-urlencoded;charset=utf-8'
    }
    data = {
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'code': code
    }
    response = requests.post(url=token_url, headers=token_headers, data=data)
    token = response.json()  # POST ????????? ???????????? return value??? JSON ???????????? ???????????? ???????????????.

    info_url = 'https://kapi.kakao.com/v2/user/me'
    info_headers = {
        'Authorization': 'Bearer ' + token['access_token'],
        'Content-type': 'application/x-www-form-urlencoded;charset=utf-8'
    }
    info_response = requests.post(url=info_url, headers=info_headers)
    infos = info_response.json()

    kakao_id = str(infos['id'])
    kakao_name = infos['properties']['nickname']

    exist = bool(db.users.find_one({'user_email': kakao_id}))
    if exist is False:
        doc = {
            'user_email': kakao_id,
            'user_name': kakao_name
        }
        db.users.insert_one(doc)

    return jsonify({'result': 'success', 'token': get_jwt_token(kakao_id)})


@application.route('/challenge', methods=['POST'])
@login_required
def save_challenge():
    challenge_host = request.user_id

    title_receive = request.form['title_give']
    decs_receive = request.form['desc_give']
    period_receive = request.form['period_give']
    address_receive = request.form['address_give']
    max_receive = int(request.form['max_give'])

    categories_receive = request.form['categories_give']
    categories = categories_receive.split(',')

    file_len = len(request.files)
    # file_len ??? 0?????? JS?????? ????????? ???????????? ???!
    # ????????? ?????????????????? default ??????????????? ????????????.
    if file_len == 0:
        full_file_name = 'default-challenge-img.jfif'  # default ???????????? ??????
    else:
        # ????????? ????????? ?????????????????? ????????? ????????? ???????????? ??????????????? ????????????.
        image_receive = request.files['image_give']

        extension = image_receive.filename.split('.')[-1]

        today = datetime.now()
        mytime = today.strftime('%Y-%m-%d-%H-%M-%S')

        filename = f'challenge-file-{mytime}'
        # save_to = f'static/assets/img/challenge/{filename}.{extension}'
        # image_receive.save(save_to)
        full_file_name = f'{filename}.{extension}'

        upload_s3(image_receive, full_file_name)

    doc = {
        'challenge_title': title_receive,
        'challenge_desc': decs_receive,
        'challenge_img': full_file_name,
        'challenge_startTime': period_receive.split(',')[0],
        'challenge_endTime': period_receive.split(',')[1],
        'challenge_address': address_receive,
        'challenge_host': challenge_host,
        'challenge_categories': categories,
        'challenge_status': 0,
        'challenge_max': max_receive
    }

    db.challenge.insert_one(doc)

    return jsonify({'msg': '????????? ?????? ???????????????.'})


@application.route('/challenges', methods=['GET'])
def show_challenge():
    challenges = object_id_decoder(list(db.challenge.find({})))
    set_challenges_people(challenges)
    return jsonify({'challenges': challenges})


@application.route('/challenge', methods=['PUT'])
def pause_challenge():
    challenge_id = request.form['challengeId_give']
    pause_receive = int(request.form['pause_give'])
    if pause_receive == 0:
        db.challenge.update_one({'_id': ObjectId(challenge_id)}, {'$set': {'challenge_status': 1}})
        return jsonify({'result': 'success', 'msg': '???????????? ?????? ???????????????.'})
    else:
        db.challenge.update_one({'_id': ObjectId(challenge_id)}, {'$set': {'challenge_status': 0}})
        return jsonify({'result': 'success', 'msg': '???????????? ????????? ???????????????.'})


@application.route('/challenge', methods=['DELETE'])
@login_required
def delete_challenge():
    challenge_id = request.form['challengeId_give']
    result = bool(db.challenge.find_one({"_id": ObjectId(challenge_id), "challenge_host": request.user_id}))
    print(result)
    if result:
        delete_join_data(challenge_id)
        delete_challenge_date(challenge_id)
        return jsonify({'result': 'success', 'msg': '????????? ?????? ???????????????.'})
    else:
        return jsonify({'result': 'Fail', 'msg': '????????? ????????????..'})


@application.route('/challenge/cancel', methods=['DELETE'])
@login_required
def cancel_challenge():
    challenge_id = request.form['challengeId_give']
    user_receive = request.user_id

    join_list = list(db.join.find({'join_challenge': challenge_id, 'join_user': user_receive}))

    # s3 ??????????????? ?????? ??????
    s3 = boto3.resource('s3')
    # ????????? ?????? ????????? ??????
    for join in join_list:
        s3.Object(os.environ['BUCKET_NAME'], join['join_img']).delete()

    db.join.delete_many({'join_challenge': challenge_id, 'join_user': user_receive})
    return jsonify({'result': 'success', 'msg': '?????? ??????????????? ?????? ???????????????.'})


@application.route('/challenge/check', methods=['POST'])
@login_required
def challenge_check():
    user_id = request.user_id

    user_name = db.users.find_one({'user_email': user_id})['user_name']
    challenge_receive = request.form['challenge_give']
    cont_receive = request.form['cont_give']
    image_receive = request.files['img_give']

    extension = image_receive.filename.split('.')[-1]

    today = datetime.now()
    mytime = today.strftime('%Y-%m-%d-%H-%M-%S')
    uploadtime = today.strftime('%Y-%m-%d')

    filename = f'join-file-{mytime}'
    # save_to = f'static/assets/img/join/{filename}.{extension}'
    # file.save(save_to)
    full_file_name = f'{filename}.{extension}'

    join = db.join.find_one({'join_challenge': challenge_receive,
                             'join_user': user_id,
                             'join_date': uploadtime
                             }, {'_id': False})
    if join is not None:
        return jsonify({'msg': '????????? ????????? ?????? ?????? ?????????.'})

    upload_s3(image_receive, full_file_name)

    doc = {
        'join_challenge': challenge_receive,
        'join_date': uploadtime,
        'join_user': user_id,
        'join_user_name': user_name,
        'join_cont': cont_receive,
        'join_img': full_file_name
    }

    db.join.insert_one(doc)

    return jsonify({'msg': '????????? ?????? ???????????????.'})


def object_id_decoder(list):
    results = []
    for document in list:
        document['_id'] = str(document['_id'])
        results.append(document)
    return results


# ????????? ???????????? ??? ????????? ????????? ??? set
def set_challenges_people(challenges):
    for challenge in challenges:
        challenge['people'] = len(list(db.join.distinct('join_user', {'join_challenge': challenge['_id']})))


# jwt ?????? ??????
def get_jwt_token(user_id):
    payload = {
        'id': user_id,
        'exp': datetime.utcnow() + timedelta(seconds=60 * 60 * 24)  # ????????? 24?????? ??????
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')  # ????????? ????????????

    # response = make_response(redirect(url_for('main_page')))  # ????????? ???????????? ????????? ??????(?)
    # response.set_cookie(TOKEN_NAME, token)  # ??????????????? ???????????? ?????? ??????(?)
    return token


# DB, S3?????? ????????? ????????? ??????
def delete_challenge_date(challenge_id):
    challenge_img = db.challenge.find_one({'_id': ObjectId(challenge_id)})['challenge_img']
    s3 = boto3.resource('s3')
    # ????????? S3 ????????? ??????
    if challenge_img != 'default-challenge-img.jfif':
        s3.Object(os.environ['BUCKET_NAME'], challenge_img).delete()
    # ????????? DB ????????? ??????
    db.challenge.delete_one({'_id': ObjectId(challenge_id)})


# DB, S3?????? ????????? ?????? ????????? ??????
def delete_join_data(challenge_id):
    join_list = list(db.join.find({'join_challenge': challenge_id}))
    s3 = boto3.resource('s3')
    # ????????? ?????? S3 ????????? ??????
    for join in join_list:
        s3.Object(os.environ['BUCKET_NAME'], join['join_img']).delete()
    # ????????? ?????? DB ????????? ??????
    db.join.delete_many({'join_challenge': challenge_id})


# s3 ????????? ????????? ?????? ?????????
def upload_s3(image_receive, full_file_name):
    s3 = boto3.client('s3',
                      aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
                      aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY']
                      )
    s3.put_object(
        ACL='public-read',
        Bucket=os.environ['BUCKET_NAME'],
        Body=image_receive,
        Key=full_file_name,
        ContentType=image_receive.content_type
    )


# scheduler code start
scheduler = BackgroundScheduler()


@scheduler.scheduled_job('cron', hour='00', minute='00', id='schedule-job', timezone='Asia/Seoul')
def challenge_scheduler():
    today = datetime.now()
    yesterday = today - timedelta(1)
    date = yesterday.strftime('%Y-%m-%d')
    db.challenge.update_many({'challenge_endTime': date}, {'$set': {'challenge_status': 2}})


scheduler.start()
# scheduler code end


if __name__ == '__main__':
    application.debug = True
    application.run()

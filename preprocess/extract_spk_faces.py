'''
具体来讲如果一个视频中只有一个人脸那么当前人脸就作为当前的视觉信息。如果当前视频帧包含两个人那么判断那个人是说话人。
具体做法是首先将对话中比较显著的人脸检测出来，根据所在的时间确定属于A还是B，这样会得到A的几张脸，记作FaceA 和B的几张脸 记做 FaceB。
Note: TalkNet 有对所有的视频进行帧率的转换，所以不需要考虑帧率的问题
conda activate TalkNet / talknet

目前的方案:
# 两张脸的情况, 存储每一帧的情况两个人脸的坐标.
>>>a = pkl.load(open('fendou_1/pywork/faces.pckl', 'rb'))
>>>a[0]
[{'frame': 0, 'bbox': [592.8956909179688, 73.52586364746094, 712.7017822265625, 211.9091033935547], 'conf': 0.9999445676803589}, 
 {'frame': 0, 'bbox': [421.4970397949219, 158.5673065185547, 512.3919067382812, 271.0180358886719], 'conf': 0.9899325370788574}]
# tracks 和 scores 文件是一一对应的, crops之后的视频片段进行处理的, 并每个cropsegment内计算得分 
>>>b = pkl.load(open('fendou_1/pywork/scores.pckl', 'rb'))
>>>[len(bi) for bi in b]
[136, 136, 206, 206, 59, 939, 939]
# 长度为7, 是视频crop的长度, 每个cropsegment内计算得分 
>>>c = pkl.load(open('fendou_1/pywork/tracks.pckl', 'rb'))
>>>c[0]
{'track': {'frame': [1,2,3,4,...], 'bbox':[[592.89569092,  73.52586365, 712.70178223, 211.90910339], ...]}
'proc_track': {'x':[], 'y':[], 's':[]}}
# 在tracks 和 scores 文件里面如果没有人脸，那么没有对应的人脸的 frame-id

# 人脸特征提取特征进行对比和聚类 --OnLeo
https://github.com/deepinsight/insightface
pip install -U insightface
选用WebFace12M模型: https://drive.google.com/file/d/1N0GL-8ehw_bz2eZQWz2b0A5XBdXdxZhg/view?usp=sharing
'''

import glob
import os, cv2
from re import T
import numpy as np
import collections

from numpy.ma.core import flatten_structured_array
import scipy as sp
from FileOps import read_csv, read_pkl, read_file, write_pkl

def get_spk2timestamps(meta_filepath):
    # 返回指定对话的说话人和时间信息
    dialog2spk2timestamps = collections.OrderedDict()
    spk2timestamps = {}
    instances = read_csv(meta_filepath, delimiter=';', skip_rows=1)
    previous_dialog_id = '_'.join(instances[0][0].split('_')[:2])
    total_rows = 0
    for instance in instances:
        UtteranceId = instance[0]
        if UtteranceId is None:
            continue
        total_rows += 1
        dialog_id = '_'.join(UtteranceId.split('_')[:2])
        if previous_dialog_id != dialog_id:
            # print('current save dialog {}'.format(previous_dialog_id))
            # print(spk2timestamps)
            assert len(spk2timestamps) == 2
            dialog2spk2timestamps[previous_dialog_id] = spk2timestamps
            spk2timestamps = {}
            previous_dialog_id = dialog_id
            # first one of another dialog
            start_time, end_time = instance[1], instance[2]
            spk = instance[4].replace(' ', '')
            spk2timestamps[spk] = [[start_time, end_time]]
        else:
            start_time, end_time = instance[1], instance[2]
            spk = instance[4].replace(' ', '')
            if spk2timestamps.get(spk) is None:
                spk2timestamps[spk] = [[start_time, end_time]]
            else:
                spk2timestamps[spk] += [[start_time, end_time]]
    # final one dialog
    dialog2spk2timestamps[dialog_id] = spk2timestamps
    # final check the lens of dialog
    total_utts = 0
    for dialog_id in dialog2spk2timestamps.keys():
        for spk in dialog2spk2timestamps[dialog_id].keys():
            total_utts += len(dialog2spk2timestamps[dialog_id][spk])
    assert total_utts == total_rows
    return dialog2spk2timestamps

def transtime2frames(timestamp):
    # 不需要考虑fps的问题，经过验证，目前的都是合适的
    frames = []
    start_time, end_time = timestamp[0], timestamp[1]
    # print(start_time, end_time)
    h, m, s, fs = start_time.split(':')
    start_frame_idx = int(m)* 60 * 25  + int(s) * 25 + int(fs)
    h, m, s, fs = end_time.split(':')
    end_frame_idx = int(m)* 60 * 25 + int(s) * 25 + int(fs)
    frames = list(range(start_frame_idx, end_frame_idx+1))
    # print(timestamp, frames)
    return frames

def get_spk_active_high_quality_info(talkout_dialog_dir, spk2timestamps):
    '''
    以dialog为单位，在每个dialog内进行说话人的检测. 默认都是25帧每秒.
    根据ASD结果文件 tracks 和 scores 中的 frameID、得分、spk的时间戳，每个spk获取confidence最高的10张人脸(top10, confidence>0)
    如果某个说话人没有 condidence 脸, None.
    返回对应的帧以及对应的坐标: {'A': {'frame_idx': [], 'frame_idx': [], 'frame_idx': []}, 'B': {}}
    并进行剪切并保存改图片 topconf_faces/Atop1_frame_idx.jpg, ... , topconf_faces/Btop1_frame_idx.jpg.jpg, ...
    return: {'A':[frame2score, frame2bbox],  'A':[frame2score, frame2bbox]}
    '''
    # 根据time_step得到那些帧属于SpeakerA 哪些帧属于 SpeakerB
    spk2frames = {}
    for spk in spk2timestamps.keys():
        timestamps = spk2timestamps[spk]
        for timestamp in timestamps:
            frames = transtime2frames(timestamp)
            if spk2frames.get(spk) is None:
                spk2frames[spk] = frames
            else:
                spk2frames[spk] += frames
    # 获取所有帧以及对应的scores.
    frame_id2score = collections.OrderedDict()
    frame_id2bbox = collections.OrderedDict()
    tracks_filepath = os.path.join(talkout_dialog_dir, 'pywork', 'tracks.pckl')
    tracks = read_pkl(tracks_filepath)
    scores_filepath = os.path.join(talkout_dialog_dir, 'pywork', 'scores.pckl')
    scores = read_pkl(scores_filepath) # [segments, framesineachsegment]
    assert len(tracks) >= len(scores)
    for crop_id in range(len(scores)):
        crop_scores = scores[crop_id]
        crop_frames = tracks[crop_id]['track']['frame'][:len(crop_scores)]
        crop_bboxs = tracks[crop_id]['track']['bbox'][:len(crop_scores)]
        for frame_idx, score, crop_bbox in zip(crop_frames, crop_scores, crop_bboxs):
            frame_id2score[frame_idx] = score
            frame_id2bbox[frame_idx] = crop_bbox
    # 对每个spk内所有帧进行排序
    result = {}
    spk2count = {}
    for spk in spk2frames.keys():
        s_frames = spk2frames[spk]
        s_frame2score = collections.OrderedDict()
        s_frame2bbox = collections.OrderedDict()
        select_frames = []
        # 选取得分大约0的帧
        for frame in s_frames:
            if frame_id2score.get(frame) is not None:
                if frame_id2score[frame] > 0:
                    select_frames.append(frame_id2score[frame])
        # 然后均匀采样
        # if select_frames 
        # if len(select_frames) > 50:
        #     select_indexs = np.linspace(1, len(select_frames), 10, dtype=int)
        #     select_frames = [select_frames[idx] for idx in select_indexs]
        # for frame in select_frames:
        spk2count[spk] = len(select_frames)
        # result[spk] = [s_frame2score, s_frame2bbox]
    return result, spk2count

def visual_high_quality_face(talkout_dialog_dir, spk2active_high_quality):
    '''
    spk2active_high_quality = {'A':[frame2score, frame2bbox],  'A':[frame2score, frame2bbox]}
    return: talkout_dialog_dir/top_faces
    '''
    # visualize the highquality faces 
    visual_faces_dir = os.path.join(talkout_dialog_dir, 'top_faces')
    if not os.path.exists(visual_faces_dir):
        os.mkdir(visual_faces_dir)
    frames_dir = os.path.join(talkout_dialog_dir, 'pyframes')
    for spk in spk2active_high_quality.keys():
        spk_frame2score, spk_frame2bbox = spk2active_high_quality[spk]
        assert len(spk_frame2score) == len(spk_frame2bbox)
        # print(spk_frame2score)
        # print(spk_frame2bbox)
        for frame_id in spk_frame2bbox.keys():
            # frame_id 从0开始的, ffmpeg 抽的帧是从 1 开始的，所以这里 frame_id + 1 对应的是真实的图片
            frame_filepath = os.path.join(frames_dir, '{:06d}.jpg'.format(frame_id+1))
            assert os.path.exists(frame_filepath) == True
            face_filepath = os.path.join(visual_faces_dir, '{}_{:06d}_{:.2f}.jpg'.format(spk, frame_id, spk_frame2score[frame_id]))
            img = cv2.imread(frame_filepath)
            bbox = spk_frame2bbox[frame_id]
            x1, y1, x2, y2 = bbox  #分别是左上角的坐标和右下角的坐标
            # 如果坐标是负值, 设置为0, 卡到边界, 左上为(0,0)
            x1, y1 = max(x1, 0), max(y1, 0)
            face_crop = img[int(y1):int(y2), int(x1):int(x2)] # 进行截取
            cv2.imwrite(face_filepath, face_crop)

def get_one_face_embeeding(model, filepath):
    '''
    see demoexample.py, this method is ok
    '''
    img = cv2.imread(filepath)
    img = cv2.resize(img, (112, 112))
    embedding = model.get_feat(img)
    return embedding
    
def check_sim(model, spk2topface_embeddings):
    '''
    存在问题: 
        fendou_1: 但是当从正面转成侧脸脸的时候，相似度从0.90降到0.18. 同时 A 和 B 都是侧脸的时候相似度 0.22 所以这种方法不 Work.
    方案2: 采取top-frame的时候在score>0的里面进行均匀采样
    '''
    spka_avg_emb = spk2topface_embeddings['A']['avg']
    spka_embs =  [spk2topface_embeddings['A'][fid] for fid in spk2topface_embeddings['A'].keys()]
    spkb_avg_emb = spk2topface_embeddings['B']['avg']
    spkb_embs =  [spk2topface_embeddings['B'][fid] for fid in spk2topface_embeddings['B'].keys()]
    avgab_sim = model.compute_sim(spka_avg_emb, spkb_avg_emb)
    print('AB sim betweent avg emd {}'.format(avgab_sim))
    print('Avg A and each A-frame sim:')
    for i in range(len(spka_embs)):
        avga_a = model.compute_sim(spka_embs[i], spka_avg_emb)
        print('\t avga and A-{} sim: {} '.format(i, avga_a))
    print('Avg A and each B-frame sim:')
    for i in range(len(spkb_embs)):
        avga_b = model.compute_sim(spkb_embs[i], spka_avg_emb)
        print('\t avga and B-{} sim: {} '.format(i, avga_b))
    print('Avg B and each B-frame sim:')
    for i in range(len(spkb_embs)):
        avgb_b = model.compute_sim(spkb_embs[i], spkb_avg_emb)
        print('\t avgb and B-{} sim: {} '.format(i, avgb_b))
    print('Avg B and each A-frame sim:')
    for i in range(len(spka_embs)):
        avgb_a = model.compute_sim(spka_embs[i], spkb_avg_emb)
        print('\t avgb and A-{} sim: {} '.format(i, avgb_a))


def get_spk_top_face_embeddings(model, top_faces_dir, spk_face_embeeding_filepath, do_check=False):
    '''
    {'A':{'avg':np, 'frameid':np}
    'B':{}}
    '''
    spk2topface_embeddings = {}
    for spk in ['A', 'B']:
        spk_img_filepaths = glob.glob(os.path.join(top_faces_dir, spk + '*.jpg'))
        if len(spk_img_filepaths) == 0:
            spk2topface_embeddings[spk] = None
            continue
        img2_embeddings = {}
        feats = []
        for img_filepath in spk_img_filepaths:
            img_name = img_filepath.split('/')[-1]
            emb = get_one_face_embeeding(model, img_filepath)
            img2_embeddings[img_name] = emb
            feats.append(emb)
        avg_emb = np.mean(feats, axis=0)
        img2_embeddings['avg'] = avg_emb
        spk2topface_embeddings[spk] = img2_embeddings
    assert len(spk2topface_embeddings) == 2
    write_pkl(spk_face_embeeding_filepath, spk2topface_embeddings)

    if do_check:
        print('------ Do check ----- ')
        check_sim(model, spk2topface_embeddings)

if __name__ == '__main__':    
    movies_names = read_file('movie_list.txt')
    movies_names = [movie_name.strip() for movie_name in movies_names]

    if True:
        # only run once
        for movie_name in movies_names[6:20]:
            print(f'Current movie {movie_name}')
            meta_filepath = '/data9/memoconv/memoconv_final_labels_csv/meta_{}.csv'.format(movie_name)
            talkout_dialog_dir = '/data9/memoconv/memoconv_convs_talknetoutput/{}'.format(movie_name)
            dialog2spk2timestamps = get_spk2timestamps(meta_filepath)
            # 95%以上的对话都有两个说话人
            count_no_spk = 0
            count_one_spk = 0
            for dialog_id in dialog2spk2timestamps:
                print('current {}'.format(dialog_id))
                cur_dialog_dir = os.path.join(talkout_dialog_dir, dialog_id)
                os.system('rm -r {}/top_faces'.format(cur_dialog_dir))
                spk2active_high_quality, spk2count = get_spk_active_high_quality_info(cur_dialog_dir, dialog2spk2timestamps[dialog_id])
                print(spk2count)
                # visual_high_quality_face(cur_dialog_dir, spk2active_high_quality)
                # if spk2count['A'] == 0 and spk2count['B'] == 0:
                #     count_no_spk += 1
                # elif spk2count['A'] == 0 or spk2count['B'] == 0:
                #     count_one_spk += 1
            # print(f'count_no_spk {count_no_spk} count_one_spk {count_one_spk}')


    if False:
        # step1
        # CUDA_VISIBLE_DEVICES=0 python extract_spk_faces.py 
        import insightface
        model_path = '/data9/memoconv/tools/facerecog/webface/webface_r50.onnx'
        model = insightface.model_zoo.get_model(model_path)
        model.prepare(ctx_id=0) # # given gpu id, if negative, then use cpu
        for movie_name in movies_names[0:1]:
            print(f'Current movie {movie_name}')
            meta_filepath = '/data9/memoconv/memoconv_final_labels_csv/meta_{}.csv'.format(movie_name)
            dialog2spk2timestamps = get_spk2timestamps(meta_filepath)
            for dialog_id in dialog2spk2timestamps.keys():
                print('\t current {}'.format(dialog_id))
                top_faces_dir = '/data9/memoconv/memoconv_convs_talknetoutput/{}/{}/top_faces'.format(movie_name, dialog_id)
                spk_face_embeeding_filepath = os.path.join(top_faces_dir, 'spk2embeddding.pkl')
                get_spk_top_face_embeddings(model, top_faces_dir, spk_face_embeeding_filepath, do_check=True)
                break
    if True:
        # cluster_one_dialog()
        pass

# step1: 计算每个对话中两个说话人的向量的平均值作为改说话人的 ground-truth. 
# step2: case1: 如果一个画面中只有一个人脸，判断是A还是B。保存跟A和B的得分。
#        case2: 如果画面中出现两个人脸，那么需要判断当前那个人是说话人。 
#        case3: 如果画面中出现三个人以及以上的人, 保留两个最大的人脸。同case2的处理方法。
# step3: 对每一句进行处理，根据时间戳信息和说话人信息，faces.pckl
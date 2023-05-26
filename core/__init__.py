import cv2
import numpy as np
import os

os.environ["OMP_NUM_THREADS"] = '8'
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture


class Model:
    def __init__(self, detection, depth, args, colors):
        self.detection = detection(args.od)
        self.depth = depth(args.de)
        self.src = args.source
        self.save = args.save
        self.colors = colors

        self.names = None
        self.original_img = None
        self.depth_image = None
        self.processing_image = None
        self.crop_images = None
        self.ordered_image = None
        self.K_masking_image = None
        self.G_masking_image = None
        self.selected_cluster = None

        self.filtered_K_masking_image = None
        self.filtered_G_masking_image = None

    def inference(self):
        self.detection(self.src, save=self.save)
        self.names = self.detection.result.names
        self.depth(self.src, save=self.save)
        self.original_img = self.detection.result.orig_img

        # self.processing_image = cv2.cvtColor(self.depth.plot(), cv2.COLOR_BGRA2GRAY)

    def preprocess(self):
        # self.original_img = self.detection.result.orig_img
        # self.processing_image = cv2.cvtColor(self.depth.plot(), cv2.COLOR_BGRA2GRAY)

        # for image in self.crop_images:
        #     height, width = image['depth_img'].shape
        #     kernel = np.zeros((height, width))
        #     th = int(height * 1)  # <Param 1> Default : 1
        #     x = np.full((width, th), np.linspace(0, 128, th)).transpose()
        #     kernel[height - th:, :] = x
        #     normalized_depth = image['depth_img'].copy() - kernel
        #     normalized_depth = normalized_depth.clip(min=0, max=255)
        #     image['normalized_depth'] = normalized_depth
        #     # self.processing_image = normalized_depth

        depth_img = cv2.cvtColor(self.depth.plot(), cv2.COLOR_BGRA2GRAY)
        self.depth_image = depth_img.copy()
        height, width = depth_img.shape
        kernel = np.zeros((height, width))
        th = int(height * 1)  # <Param 1> Default : 1
        x = np.full((width, th), np.linspace(0, 255, th)).transpose()
        kernel[height - th:, :] = x
        normalized_depth = depth_img - kernel
        normalized_depth = normalized_depth.clip(min=0, max=255)
        self.processing_image = normalized_depth

    def crop(self):
        detections = self.detection.result.boxes.data.detach().cpu().numpy()

        depth_img = self.processing_image
        crop_images = []
        for detection in detections:
            *box, conf, cls = detection
            if conf < 0.6:
                continue
            l, t, r, b = map(int, box)
            centroid = ((t + b) // 2, (l + r) // 2)
            crop_images.append(
                dict(cls=int(cls),
                     conf=conf,
                     depth_value=depth_img[centroid],
                     ltrb=(l, t, r, b),
                     centroid=centroid,
                     original_img=self.original_img[t:b, l:r].copy(),
                     gray_img=cv2.cvtColor(self.original_img[t:b, l:r].copy(), cv2.COLOR_BGR2GRAY),
                     depth_img=depth_img[t:b, l:r]))

        self.crop_images = sorted(crop_images, key=lambda x: x['depth_value'])

    @staticmethod
    def median(img):
        height, width = img.shape
        out2 = np.zeros((height + 4, width + 4), dtype=float)
        out2[2: 2 + height, 2: 2 + width] = img.copy().astype(float)
        temp2 = out2.copy()

        for i in range(height):
            for j in range(width):
                hybrid_temp1 = np.median((temp2[i, j], temp2[i + 1, j + 1], temp2[i + 2, j + 2],
                                          temp2[i + 3, j + 3], temp2[i + 4, j + 4]))
                hybrid_temp2 = np.median((temp2[i + 4, j], temp2[i + 3, j + 1], temp2[i + 2, j + 2],
                                          temp2[i + 1, j + 3], temp2[i, j + 4]))
                hybrid_temp3 = np.median((temp2[i: i + 5, j:j + 5]))
                out2[2 + i, 2 + j] = np.median((hybrid_temp1, hybrid_temp2, hybrid_temp3))

        out2 = out2[2:2 + height, 2:2 + width].astype(np.uint8)

        return out2

    @staticmethod
    def final_median(img):
        height, width, channel = img.shape

        out2 = np.zeros((height + 4, width + 4, channel), dtype=float)
        out2[2: 2 + height, 2: 2 + width] = img.copy().astype(float)
        temp2 = out2.copy()

        for i in range(height):
            for j in range(width):
                for k in range(channel):
                    hybrid_temp1 = np.median((temp2[i, j, k], temp2[i + 1, j + 1, k], temp2[i + 2, j + 2, k],
                                              temp2[i + 3, j + 3, k], temp2[i + 4, j + 4, k]))
                    hybrid_temp2 = np.median((temp2[i + 4, j, k], temp2[i + 3, j + 1, k], temp2[i + 2, j + 2, k],
                                              temp2[i + 1, j + 3, k], temp2[i, j + 4, k]))
                    hybrid_temp3 = np.median((temp2[i: i + 5, j:j + 5, k]))
                    out2[2 + i, 2 + j, k] = np.median((hybrid_temp1, hybrid_temp2, hybrid_temp3))

        out2 = out2[2:2 + height, 2:2 + width].astype(np.uint8)
        return out2

    def postprocess(self):
        for image in self.crop_images:
            # 이미지의 높이와 너비를 가져옵니다.

            height = image['original_img'].shape[0]
            width = image['original_img'].shape[1]

            canvas = np.full((height, width, 3), (0, 0, 0), dtype=np.uint8)

            # print(f"image['depth_img'] : {image['depth_img'].shape}")
            # print(f"image['gray_img'] : {image['gray_img'].shape}")
            # print(f"canvas : {canvas.shape}")

            canvas[:, :] = image['original_img'].copy()
            # cv2.imwrite('depth.png', image['depth_img'])
            # canvas[:, :, 1] = image['gray_img'].copy()
            # cv2.imwrite('gray.png', image['gray_img'])

            # KMeans 클러스터링 모델을 초기화합니다.
            kmeans = KMeans(n_clusters=3, n_init='auto')
            gmm = GaussianMixture(n_components=3)

            # 이미지의 픽셀을 클러스터링합니다.
            km_cluster_labels = kmeans.fit_predict(canvas.reshape(-1, 3))
            gmm_cluster_labels = gmm.fit_predict(canvas.reshape(-1, 3))

            # # 클러스터 레이블을 사용하여 군집화된 이미지를 만듭니다.
            km_clustered_image = np.zeros((height, width), dtype=np.uint8)
            gmm_clustered_image = np.zeros((height, width), dtype=np.uint8)

            # print(f'canvas.reshape(-1, 2) : {canvas.reshape(-1, 2).shape}')
            # print(f'km_clustered_image : {km_clustered_image.shape}')
            # print(f'kmeans.cluster_centers_ : {kmeans.cluster_centers_.shape}')
            # print(f'km_cluster_labels : {km_cluster_labels.shape}')
            # print('----------------')

            for i in range(height):
                for j in range(width):
                    km_clustered_image[i, j] = kmeans.cluster_centers_[km_cluster_labels[i * width + j]][0]
                    gmm_clustered_image[i, j] = gmm.means_[gmm_cluster_labels[i * width + j]][0]

            # km_clustered_image = cv2.GaussianBlur(km_clustered_image, ksize=(3, 3), sigmaX=0)

            image['K_blur'] = self.median(km_clustered_image)

            # gmm_clustered_image = cv2.GaussianBlur(gmm_clustered_image, ksize=(3, 3), sigmaX=0)

            image['G_blur'] = self.median(gmm_clustered_image)

            # self.selected_cluster = 'KMean'

            # image['KMean'] = km_clustered_image.copy()
            # image['GMM'] = gmm_clustered_image.copy()

            # val, cnt = np.unique(image['KMean'], return_counts=True)
            # vals = {int(k): v for k, v in zip(val, cnt)}
            # gv = sorted(vals.keys())
            # image['KMean_mask'] = gv[2:]
            #
            # val, cnt = np.unique(image['GMM'], return_counts=True)
            # vals = {int(k): v for k, v in zip(val, cnt)}
            # gv = sorted(vals.keys())
            # image['GMM_mask'] = gv[1:]

            ##########################################################

            # canvas = np.full((height, width, 2), (0, 0), dtype=np.uint8)
            # canvas[:, :, 0] = km_cluster_labels.reshape(height, width)
            # canvas[:, :, 1] = gmm_cluster_labels.reshape(height, width)

            fusion_img = image['K_blur'].astype(int) + image['G_blur'].astype(int)

            image['fusion'] = fusion_img.copy().clip(min=0, max=255).astype(np.uint8)

            fusion_img = ((fusion_img - fusion_img.min()) / (fusion_img.max() - fusion_img.min()) * 255).astype(
                np.uint8)

            image['normalized_fusion'] = fusion_img.copy()

            # image['fusion_mean_masking'] = fusion_img[fusion_img > fusion_img.mean()]
            image['fusion_mean_masking'] = np.where(fusion_img > fusion_img.mean(), fusion_img, 0)

            image['fmm_depth_fusion'] = (
                    image['fusion_mean_masking'].copy().astype(int) + image['depth_img'].copy().astype(int)).clip(
                min=0, max=255).astype(np.uint8)

            # print(f"image['fusion_mean_masking'] : {type(image['fusion_mean_masking'])}")
            # print(f"image['fusion_mean_masking'][0,0] : {type(image['fusion_mean_masking'][0,0])}")
            # print(f"image['depth_img'][0,0] : {type(image['depth_img'][0,0])}")

            image['fmm_depth_fusion'] = cv2.addWeighted(image['fusion_mean_masking'].copy(), 0.35,
                                                        image['depth_img'].copy().astype(np.uint8), 1, 0)

            cv2.imwrite('fmm.png', image['fmm_depth_fusion'])

            ##############################################

            canvas = np.full((height, width), 0, dtype=np.uint8)
            canvas[:, :] = image['fmm_depth_fusion'].copy()
            # canvas[:, :] = image['fusion_mean_masking'].copy()

            # canvas[:, :, 1] = image['depth_img'].copy()
            #
            # kmeans = KMeans(n_clusters=5, n_init='auto')
            # gmm = GaussianMixture(n_components=3)
            #
            # km_cluster_labels = kmeans.fit_predict(canvas.reshape(-1, 2))
            # gmm_cluster_labels = gmm.fit_predict(canvas.reshape(-1, 2))

            kmeans = KMeans(n_clusters=2, n_init='auto')
            gmm = GaussianMixture(n_components=2)

            km_cluster_labels = kmeans.fit_predict(canvas.reshape(-1, 1))
            gmm_cluster_labels = gmm.fit_predict(canvas.reshape(-1, 1))

            ###############################################

            km_clustered_image = np.zeros((height, width), dtype=np.uint8)
            gmm_clustered_image = np.zeros((height, width), dtype=np.uint8)

            # print(f"image['fusion_mean_masking'].reshape(-1, 1) : {image['fusion_mean_masking'].reshape(-1, 1).shape}")
            # print(f'km_clustered_image : {km_clustered_image.shape}')
            # print(f'kmeans.cluster_centers_ : {kmeans.cluster_centers_.shape}')
            # print(f'km_cluster_labels : {km_cluster_labels.shape}')

            for i in range(height):
                for j in range(width):
                    # print(f'i * width + j : {i * width + j}')
                    # exit()
                    km_clustered_image[i, j] = kmeans.cluster_centers_[km_cluster_labels[i * width + j]]
                    gmm_clustered_image[i, j] = gmm.means_[gmm_cluster_labels[i * width + j]]

            image['F_KMean'] = km_clustered_image.copy()
            image['F_GMM'] = gmm_clustered_image.copy()

            val, cnt = np.unique(image['F_KMean'], return_counts=True)
            vals = {int(k): v for k, v in zip(val, cnt)}
            gv = sorted(vals.keys())
            print('KMEAN', gv)
            image['F_KMean_mask'] = gv[-1:]

            # gv = sorted(vals.keys())
            # image['F_KMean_g_max'] = gv[2:]

            val, cnt = np.unique(image['F_GMM'], return_counts=True)
            vals = {int(k): v for k, v in zip(val, cnt)}
            gv = sorted(vals.keys())
            print('GMM', gv)
            image['F_GMM_mask'] = gv[-1:]

            # fusion_img = image['K_blur'].astype(int) + image['G_blur'].astype(int)
            #
            # image['fusion'] = fusion_img.copy().clip(min=0, max=255).astype(np.uint8)
            #
            # fusion_img = ((fusion_img - fusion_img.min()) / (fusion_img.max() - fusion_img.min()) * 255).astype(
            #     np.uint8)
            #
            # image['normalized_fusion'] = fusion_img.copy()
            #
            # # image['fusion_mean_masking'] = fusion_img[fusion_img > fusion_img.mean()]
            # image['fusion_mean_masking'] = np.where(fusion_img > fusion_img.mean(), fusion_img, 0)

            # new_img = image['F_KMean'].astype(int) + image['G_blur'].astype(int)

            # image['fusion'] = new_img.copy().clip(min=0, max=255).astype(np.uint8)

            # new_img = (new_img - new_img.min()) / (new_img.max() - new_img.min()) * 255
            #
            # image['normalized_fusion'] = new_img.astype(np.uint8)

            # gv = sorted(vals.keys())
            # image['F_GMM_g_max'] = gv[2:]

            # val, cnt = np.unique(image['GMM'], return_counts=True)
            # vals = {int(k): v for k, v in zip(val, cnt)}
            # gv = sorted(vals.keys())
            # image['GMM_mask'] = gv[2:]

            # exit()

            # gv = sorted(vals.keys(), key=lambda x: vals[x])
            # gd = sorted(vals.keys())
            # image['g_max'] = [i for i in gv if i > gd[0]][-3:]

            # print(f'gv : {gv}')
            # print(f'gd : {gd}')
            # print(f"image['g_max'] : {image['g_max']}")
            # image['g_min'] = gd[0]
            # if gv[-1] == gd[0] and len(gv) > 1:
            #     image['g_max'] = gv[-2:]
            # elif len(gv) > 2:
            #     image['g_max'] = gv[-2:]
            # else:
            #     image['g_max'] = gv[-1:]
            # image['g_max'] = gv[-1]
            # print(f'image["g_max"] : {image["g_max"]}')

    def ordered_paint(self):
        canvas = self.detection.plot(label=False)
        K_masking_canvas = np.zeros(canvas.shape, dtype=np.uint8)
        G_masking_canvas = np.zeros(canvas.shape, dtype=np.uint8)
        for idx, image in enumerate(self.crop_images):
            cls = image['cls']
            color = self.colors(cls, True)
            cv2.putText(canvas, str(idx + 1), image['ltrb'][:2], cv2.FONT_HERSHEY_PLAIN, 3, color, 2)
            l, t, r, b = image['ltrb']
            if image['F_KMean_mask']:
                box = K_masking_canvas[t:b, l:r]
                for g_max in image['F_KMean_mask']:
                    box[image['F_KMean'] == g_max] = color
                K_masking_canvas[t:b, l:r] = box
            if image['F_GMM_mask']:
                box = G_masking_canvas[t:b, l:r]
                for g_max in image['F_GMM_mask']:
                    box[image['F_GMM'] == g_max] = color
                G_masking_canvas[t:b, l:r] = box

        self.ordered_image = canvas
        self.K_masking_image = K_masking_canvas
        self.G_masking_image = G_masking_canvas

    def final_filter(self):
        self.filtered_K_masking_image = self.final_median(self.K_masking_image)
        self.filtered_G_masking_image = self.final_median(self.G_masking_image)

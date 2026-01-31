// 等待Vue和ElementPlus加载完成
function waitForDependencies(callback) {
    if (typeof Vue !== 'undefined' && typeof ElementPlus !== 'undefined') {
        callback();
    } else {
        setTimeout(() => waitForDependencies(callback), 100);
    }
}

function initApp() {
    if (typeof Vue === 'undefined') {
        console.error('Vue.js未加载！请检查网络连接或CDN是否可访问');
        document.body.innerHTML = '<div style="padding: 20px; text-align: center;"><h2>加载失败</h2><p>Vue.js库未加载，请检查网络连接</p></div>';
        return;
    }
    if (typeof ElementPlus === 'undefined') {
        console.error('Element Plus未加载！请检查网络连接或CDN是否可访问');
        document.body.innerHTML = '<div style="padding: 20px; text-align: center;"><h2>加载失败</h2><p>Element Plus库未加载，请检查网络连接</p></div>';
        return;
    }
    
    console.log('Vue.js和Element Plus已加载，开始初始化应用');
    
    const { createApp } = Vue;
    const { ElMessage, ElMessageBox } = ElementPlus;

    // API_BASE_URL 在 index.html 中定义并存储在 window.API_BASE_URL
    // 直接使用 window.API_BASE_URL，避免作用域冲突
    const API_BASE_URL = window.API_BASE_URL || 'http://localhost:5001/api';
    
    const app = createApp({
    data() {
        return {
            // 搜索表单
            searchForm: {
                search: '',
                user_id: ''
            },
            // 商品列表
            goodsList: [],
            // 选择模式映射表（用于存储每个商品的选择状态）
            selectingImageMap: {},
            // 分页
            pagination: {
                page: 1,
                page_size: 20,
                total: 0
            },
            // 选中的商品ID
            selectedGoods: [],
            // 图片操作弹窗
            imageActionDialogVisible: false,
            currentActionGoods: null,
            currentActionImageIndex: null,
            // 全屏原图
            fullscreenImageVisible: false,
            fullscreenImageUrl: '',
            // 加载状态
            saving: false,
            batchSaving: false,
            // 统计数据
            statistics: {
                preprocessing: 0,
                pending_upload: 0,
                discarded: 0
            },
            // 定时器
            statisticsTimer: null,
            // 消息提醒相关
            lastNotificationTime: null, // 上次推送时间
            notificationThreshold: 500, // 待上传数量阈值
            // 移动端检测
            isMobile: window.innerWidth <= 768,
            // 搜索栏显示状态（移动端默认隐藏）
            searchBarVisible: window.innerWidth > 768,
            // 移动端当前显示的商品索引（仅用于移动端模式）
            mobileCurrentIndex: 0
        };
    },
    mounted() {
        this.loadGoodsList();
        this.loadStatistics();
        // 添加ESC键监听，退出图片选择状态
        document.addEventListener('keydown', this.handleKeyDown);
        // 添加点击事件监听，点击非目标区域退出选择状态
        document.addEventListener('click', this.handleDocumentClick);
        // 设置定时刷新统计数据（每10秒）
        this.statisticsTimer = setInterval(() => {
            this.loadStatistics();
        }, 10000);
        // 从localStorage恢复上次推送时间
        const savedTime = localStorage.getItem('lastNotificationTime');
        if (savedTime) {
            this.lastNotificationTime = parseInt(savedTime, 10);
        }
        // 监听窗口大小变化，更新移动端状态
        window.addEventListener('resize', this.handleResize);
        this.handleResize();
        // 初始化主内容区域间距
        this.updateMainContentMargin();
    },
    beforeUnmount() {
        // 清理定时器
        if (this.statisticsTimer) {
            clearInterval(this.statisticsTimer);
        }
        // 清理事件监听
        document.removeEventListener('keydown', this.handleKeyDown);
        document.removeEventListener('click', this.handleDocumentClick);
        window.removeEventListener('resize', this.handleResize);
    },
    methods: {
        // 加载统计数据
        async loadStatistics() {
            try {
                const response = await axios.get(`${API_BASE_URL}/goods/statistics`);
                if (response.data.code === 0) {
                    const oldPendingUpload = this.statistics.pending_upload || 0;
                    this.statistics = response.data.data;
                    
                    // 检查是否需要发送提醒
                    const newPendingUpload = this.statistics.pending_upload || 0;
                    if (newPendingUpload > this.notificationThreshold) {
                        await this.checkAndSendNotification(newPendingUpload);
                    }
                }
            } catch (error) {
                console.error('加载统计数据失败:', error);
                // 静默失败，不影响主流程
            }
        },
        // 检查并发送企业微信提醒
        async checkAndSendNotification(pendingUploadCount) {
            try {
                const now = Date.now();
                const oneHour = 60 * 60 * 1000; // 1小时的毫秒数
                
                // 检查距离上次推送是否超过1小时
                if (this.lastNotificationTime && (now - this.lastNotificationTime) < oneHour) {
                    console.log('[消息提醒] 距离上次推送不足1小时，跳过');
                    return;
                }
                
                // 发送Webhook消息
                const webhookUrl = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=364a2227-4ff7-4488-ac04-fa66c691a061';
                const messageBody = {
                    msgtype: 'text',
                    text: {
                        content: `待上传商品已超过${pendingUploadCount}，可以操作上传了`
                    }
                };
                
                const response = await axios.post(webhookUrl, messageBody, {
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                if (response.data.errcode === 0) {
                    console.log('[消息提醒] 企业微信消息推送成功');
                    this.lastNotificationTime = now;
                    // 保存到localStorage，避免刷新后重复推送
                    localStorage.setItem('lastNotificationTime', now.toString());
                } else {
                    console.error('[消息提醒] 企业微信消息推送失败:', response.data.errmsg);
                }
            } catch (error) {
                console.error('[消息提醒] 发送提醒失败:', error);
                // 静默失败，不影响主流程
            }
        },
        // 加载商品列表
        async loadGoodsList() {
            try {
                const params = {
                    page: this.pagination.page,
                    page_size: this.pagination.page_size,
                    ...this.searchForm
                };
                
                // 移动端特殊逻辑：如果是移动端且没有搜索关键词，默认只查待审核商品
                if (this.isMobile && !this.searchForm.search && !this.searchForm.user_id) {
                    params.review_status = 0;
                    params.process_status = 2;
                    params.order_by = 'api_id_asc'; // 按 api_id 正序，取第一个非绿色（待审核）商品
                    params.page_size = 1; // 移动端只取一条
                }
                
                const response = await axios.get(`${API_BASE_URL}/goods/list`, { params });
                
                if (response.data.code === 0) {
                    // 处理商品列表
                    this.goodsList = response.data.data.list;
                    // 初始化选择状态映射表
                    this.goodsList.forEach(goods => {
                        if (!this.selectingImageMap[goods.id]) {
                            this.$set ? this.$set(this.selectingImageMap, goods.id, undefined) :
                                       (this.selectingImageMap[goods.id] = undefined);
                        }
                    });
                    this.pagination.total = response.data.data.total;
                } else {
                    ElMessage.error(response.data.message || '加载失败');
                }
            } catch (error) {
                console.error('加载商品列表失败:', error);
                const msg = error.response?.data?.message || error.message || '网络错误';
                ElMessage.error('加载商品列表失败: ' + msg);
            }
        },
        // 搜索
        handleSearch() {
            this.pagination.page = 1;
            this.loadGoodsList();
        },
        // 重置搜索
        handleReset() {
            this.searchForm = {
                search: '',
                user_id: ''
            };
            this.pagination.page = 1;
            this.loadGoodsList();
        },
        // 分页大小改变
        handleSizeChange(size) {
            this.pagination.page_size = size;
            this.pagination.page = 1;
            this.loadGoodsList();
        },
        // 页码改变
        handlePageChange(page) {
            this.pagination.page = page;
            this.loadGoodsList();
        },
        // 选择商品
        handleSelectGoods() {
            // 已通过v-model自动处理
        },
        // 处理checkbox变化
        handleCheckboxChange(goodsId, checked) {
            if (checked) {
                if (!this.selectedGoods.includes(goodsId)) {
                    this.selectedGoods.push(goodsId);
                }
            } else {
                const index = this.selectedGoods.indexOf(goodsId);
                if (index > -1) {
                    this.selectedGoods.splice(index, 1);
                }
            }
        },
        // 显示图片操作选择弹窗
        showImageActionDialog(goods, imageIndex) {
            this.currentActionGoods = goods;
            this.currentActionImageIndex = imageIndex;
            this.imageActionDialogVisible = true;
        },
        // 从弹窗中选择操作
        async handleActionFromDialog(action) {
            const goods = this.currentActionGoods;
            const imageIndex = this.currentActionImageIndex;
            
            // 关闭弹窗
            this.imageActionDialogVisible = false;
            
            if (action === 'replace-main') {
                // 更换主图
                if (imageIndex === 0) {
                    ElMessage.warning('选中的图片已经是主图');
                    return;
                }
                
                try {
                    const response = await axios.post(`${API_BASE_URL}/goods/replace-main-image`, {
                        id: goods.id,
                        source_index: imageIndex
                    });
                    
                    if (response.data.code === 0) {
                        ElMessage.success('主图已更换，所有规格图已更新');
                        await this.refreshGoodsItem(goods.id);
                    } else {
                        ElMessage.error(response.data.message || '操作失败');
                    }
                } catch (error) {
                    console.error('更换主图失败:', error);
                    ElMessage.error('操作失败: ' + (error.message || '网络错误'));
                }
            } else if (action === 'approve') {
                // 审核通过
                await this.handleApprove(goods);
            } else if (action === 'replace-third') {
                // 更换第3张图
                if (imageIndex === 2) {
                    ElMessage.warning('选中的图片已经是第3张');
                    return;
                }
                
                if (!goods.image_list || goods.image_list.length < 3) {
                    ElMessage.warning('该商品轮播图不足3张，无法更换');
                    return;
                }
                
                try {
                    const response = await axios.post(`${API_BASE_URL}/goods/swap-image`, {
                        id: goods.id,
                        source_index: imageIndex,
                        target_index: 2
                    });
                    
                    if (response.data.code === 0) {
                        ElMessage.success('第3张图已更换');
                        await this.refreshGoodsItem(goods.id);
                    } else {
                        ElMessage.error(response.data.message || '操作失败');
                    }
                } catch (error) {
                    console.error('更换第3张图失败:', error);
                    ElMessage.error('操作失败: ' + (error.message || '网络错误'));
                }
            } else if (action === 'remove') {
                // 删除轮播图
                if (!goods.image_list || goods.image_list.length <= 1) {
                    ElMessage.warning('轮播图只剩一张，无法删除');
                    return;
                }
                
                // 二次确认
                try {
                    await ElMessageBox.confirm(
                        `确定要删除第${imageIndex + 1}张图片吗？`,
                        '删除确认',
                        {
                            confirmButtonText: '确定',
                            cancelButtonText: '取消',
                            type: 'warning'
                        }
                    );
                    
                    const response = await axios.post(`${API_BASE_URL}/goods/remove-image`, {
                        id: goods.id,
                        image_index: imageIndex
                    });
                    
                    if (response.data.code === 0) {
                        ElMessage.success('图片已删除');
                        await this.refreshGoodsItem(goods.id);
                    } else {
                        ElMessage.error(response.data.message || '操作失败');
                    }
                } catch (error) {
                    if (error !== 'cancel') {
                        console.error('删除图片失败:', error);
                        ElMessage.error('操作失败: ' + (error.message || '网络错误'));
                    }
                }
            } else if (action === 'discard') {
                // 废弃商品
                await this.handleDiscard(goods);
            }
            
            // 清空临时数据
            this.currentActionGoods = null;
            this.currentActionImageIndex = null;
        },
        // 批量保存
        async handleBatchSave() {
            if (this.selectedGoods.length === 0) {
                ElMessage.warning('请先选择要保存的商品');
                return;
            }
            
            try {
                await ElMessageBox.confirm(
                    `确定要批量保存 ${this.selectedGoods.length} 个商品吗？`,
                    '批量保存确认',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                this.batchSaving = true;
                try {
                    const response = await axios.post(`${API_BASE_URL}/goods/batch-save`, {
                        goods_ids: this.selectedGoods
                    });
                    
                    if (response.data.code === 0) {
                        const data = response.data.data;
                        ElMessage.success(
                            `批量保存完成！成功: ${data.success_count}, 失败: ${data.error_count}`
                        );
                        
                        if (data.errors && data.errors.length > 0) {
                            console.error('保存失败的商品:', data.errors);
                        }
                        
                        this.selectedGoods = [];
                        this.loadGoodsList();
                    } else {
                        ElMessage.error(response.data.message || '批量保存失败');
                    }
                } catch (error) {
                    console.error('批量保存失败:', error);
                    ElMessage.error('批量保存失败: ' + (error.message || '网络错误'));
                } finally {
                    this.batchSaving = false;
                }
            } catch (error) {
                // 用户取消
            }
        },
        // 废弃商品
        async handleDiscard(goods) {
            try {
                await ElMessageBox.confirm(
                    '确定要废弃这个商品吗？标题将添加【⚠️已废弃】前缀。',
                    '废弃确认',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                const response = await axios.post(`${API_BASE_URL}/goods/discard`, {
                    id: goods.id
                });
                
                if (response.data.code === 0) {
                    ElMessage.success('商品已标记为废弃');
                    // 移动端：直接加载下一条；PC端：刷新当前项
                    if (this.isMobile) {
                        await this.loadGoodsList();
                    } else {
                        await this.refreshGoodsItem(goods.id);
                    }
                    // 立即刷新统计数据
                    this.loadStatistics();
                } else {
                    ElMessage.error(response.data.message || '操作失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('废弃商品失败:', error);
                    ElMessage.error('操作失败: ' + (error.message || '网络错误'));
                }
            }
        },
        // 审核通过
        async handleApprove(goods) {
            try {
                const response = await axios.post(`${API_BASE_URL}/goods/approve`, {
                    id: goods.id
                });
                
                if (response.data.code === 0) {
                    ElMessage.success(response.data.message || '商品已审核通过');
                    // 移动端：直接加载下一条；PC端：刷新当前项
                    if (this.isMobile) {
                        await this.loadGoodsList();
                    } else {
                        await this.refreshGoodsItem(goods.id);
                    }
                    // 立即刷新统计数据
                    this.loadStatistics();
                } else {
                    ElMessage.error(response.data.message || '操作失败');
                }
            } catch (error) {
                console.error('审核商品失败:', error);
                ElMessage.error('操作失败: ' + (error.message || '网络错误'));
            }
        },
        // 更换第3张图（保留作为备用，通过按钮调用）
        handleReplaceThirdImage(goods) {
            if (!goods.image_list || goods.image_list.length < 3) {
                ElMessage.warning('该商品轮播图不足3张，无法更换');
                return;
            }
            
            ElMessage.info('请在轮播图中点选出一张作为第3张图');
            this.selectingImageMap = {
                ...this.selectingImageMap,
                [goods.id]: 'third'
            };
        },
        // 更换主图（保留作为备用，通过按钮调用）
        handleReplaceMainImage(goods) {
            if (!goods.image_list || goods.image_list.length === 0) {
                ElMessage.warning('该商品没有轮播图');
                return;
            }
            
            ElMessage.info('请在轮播图中点选出一张作为主图');
            this.selectingImageMap = {
                ...this.selectingImageMap,
                [goods.id]: 'main'
            };
        },
        // 删除轮播图（保留作为备用，通过按钮调用）
        handleRemoveImage(goods) {
            if (!goods.image_list || goods.image_list.length === 0) {
                ElMessage.warning('该商品没有轮播图');
                return;
            }
            
            if (goods.image_list.length <= 1) {
                ElMessage.warning('轮播图只剩一张，无法删除');
                return;
            }
            
            ElMessage.info('请在轮播图中点选出一张要删除的图片');
            this.selectingImageMap = {
                ...this.selectingImageMap,
                [goods.id]: 'remove'
            };
        },
        // 处理图片选择
        async handleImageSelect(goods, index, event) {
            // 阻止事件冒泡到document，防止handleDocumentClick清空映射表
            if (event) {
                event.stopPropagation();
            }
            
            // 从映射表获取选择状态
            const selectingMode = this.selectingImageMap[goods.id];
            
            console.log('点击图片，索引:', index, '选择模式:', selectingMode, '商品ID:', goods.id);
            console.log('当前映射表状态:', JSON.parse(JSON.stringify(this.selectingImageMap)));
            console.log('映射表中该商品的值:', this.selectingImageMap[goods.id]);
            console.log('映射表所有键:', Object.keys(this.selectingImageMap));
            
            if (!selectingMode) {
                console.log('不在选择模式，忽略点击');
                return; // 不在选择模式，不处理
            }
            
            if (selectingMode === 'third') {
                // 更换第3张图
                if (index === 2) {
                    ElMessage.warning('选中的图片已经是第3张');
                    this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                    return;
                }
                
                try {
                    const response = await axios.post(`${API_BASE_URL}/goods/swap-image`, {
                        id: goods.id,
                        source_index: index,
                        target_index: 2
                    });
                    
                    if (response.data.code === 0) {
                        ElMessage.success('第3张图已更换');
                        this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                        // 刷新该商品的数据
                        await this.refreshGoodsItem(goods.id);
                    } else {
                        ElMessage.error(response.data.message || '操作失败');
                        this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                    }
                } catch (error) {
                    console.error('更换第3张图失败:', error);
                    ElMessage.error('操作失败: ' + (error.message || '网络错误'));
                    this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                }
            } else if (selectingMode === 'main') {
                // 更换主图
                if (index === 0) {
                    ElMessage.warning('选中的图片已经是主图');
                    this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                    return;
                }
                
                try {
                    const response = await axios.post(`${API_BASE_URL}/goods/replace-main-image`, {
                        id: goods.id,
                        source_index: index
                    });
                    
                    if (response.data.code === 0) {
                        ElMessage.success('主图已更换，所有规格图已更新');
                        this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                        // 刷新该商品的数据
                        await this.refreshGoodsItem(goods.id);
                    } else {
                        ElMessage.error(response.data.message || '操作失败');
                        this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                    }
                } catch (error) {
                    console.error('更换主图失败:', error);
                    ElMessage.error('操作失败: ' + (error.message || '网络错误'));
                    this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                }
            } else if (selectingMode === 'remove') {
                // 删除轮播图
                if (goods.image_list.length <= 1) {
                    ElMessage.warning('轮播图只剩一张，无法删除');
                    this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                    return;
                }
                
                // 二次确认
                try {
                    await ElMessageBox.confirm(
                        `确定要删除第${index + 1}张图片吗？`,
                        '删除确认',
                        {
                            confirmButtonText: '确定',
                            cancelButtonText: '取消',
                            type: 'warning'
                        }
                    );
                } catch {
                    // 用户取消
                    this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                    return;
                }
                
                try {
                    const response = await axios.post(`${API_BASE_URL}/goods/remove-image`, {
                        id: goods.id,
                        image_index: index
                    });
                    
                    if (response.data.code === 0) {
                        ElMessage.success('图片已删除');
                        this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                        // 刷新该商品的数据
                        await this.refreshGoodsItem(goods.id);
                    } else {
                        ElMessage.error(response.data.message || '操作失败');
                        this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                    }
                } catch (error) {
                    console.error('删除图片失败:', error);
                    ElMessage.error('操作失败: ' + (error.message || '网络错误'));
                    this.selectingImageMap = { ...this.selectingImageMap, [goods.id]: undefined };
                }
            }
        },
        // 刷新单个商品数据
        async refreshGoodsItem(goodsId) {
            try {
                // 获取商品详情
                const response = await axios.get(`${API_BASE_URL}/goods/detail/${goodsId}`);
                
                if (response.data.code === 0) {
                    const updatedGoods = response.data.data;
                    
                    // 处理JSON字段
                    if (updatedGoods.image_list) {
                        try {
                            updatedGoods.image_list = typeof updatedGoods.image_list === 'string' 
                                ? JSON.parse(updatedGoods.image_list) 
                                : updatedGoods.image_list;
                        } catch {
                            updatedGoods.image_list = [];
                        }
                    }

                    // 同样处理 carousel_labels，防止后端未解析
                    if (updatedGoods.carousel_labels) {
                        try {
                            updatedGoods.carousel_labels = typeof updatedGoods.carousel_labels === 'string'
                                ? JSON.parse(updatedGoods.carousel_labels)
                                : updatedGoods.carousel_labels;
                        } catch {
                            updatedGoods.carousel_labels = [];
                        }
                    }
                    
                    // 更新列表中的商品数据
                    const index = this.goodsList.findIndex(g => g.id === goodsId);
                    if (index !== -1) {
                        // 保留选择状态
                        const wasSelected = this.selectedGoods.includes(goodsId);
                        // 更新商品数据
                        this.goodsList[index] = updatedGoods;
                        // 清除选择状态（从映射表中清除）
                        const newMap = { ...this.selectingImageMap };
                        delete newMap[goodsId];
                        this.selectingImageMap = newMap;
                        // 如果之前被选中，确保还在选中列表中
                        if (wasSelected && !this.selectedGoods.includes(goodsId)) {
                            this.selectedGoods.push(goodsId);
                        }
                    }
                }
            } catch (error) {
                console.error('刷新商品数据失败:', error);
                // 如果刷新失败，重新加载整个列表
                this.loadGoodsList();
            }
        },
        // 图片加载错误处理
        handleImageError(event) {
            // 修复：将"图片加载中文"改为"图片加载中"
            event.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iI2U0ZTdlZCIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjE0IiBmaWxsPSIjOTA5Mzk5IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+5Zu+54mH5Yqg6L295LitPC90ZXh0Pjwvc3ZnPg==';
        },
        // 生成缩略图URL（添加缩略图参数，加快加载速度）
        // size: 移动端列表 100x，桌面端列表 200x，弹窗 300x
        getThumbnailUrl(url, size = 200) {
            if (!url || typeof url !== 'string') return url;
            const baseUrl = url.split('?')[0];
            return `${baseUrl}?imageMogr2/thumbnail/${size}x`;
        },
        // 归一化 URL 用于匹配（去查询串、尾部斜杠等、忽略协议）
        normalizeLabelUrl(url) {
            if (!url || typeof url !== 'string') return '';
            // 移除协议头(http/https)，移除查询参数，移除尾部斜杠
            return url.split('?')[0].replace(/^https?:\/\//, '').replace(/\/+$/, '');
        },
        // 按「当前这张图的 URL」在 carousel_labels 里找标签（工作流按 original_url 记录，删图/调序后仍对得上）
        // 增强：优先按 URL 匹配，匹配不到则尝试按索引匹配（后端承诺同序）
        getImageLabel(goods, index) {
            const labels = goods && goods.carousel_labels && Array.isArray(goods.carousel_labels) ? goods.carousel_labels : [];
            const imgList = goods && goods.image_list && Array.isArray(goods.image_list) ? goods.image_list : [];
            
            let lab = null;
            const currentUrl = imgList[index];

            // 1. 尝试 URL 匹配
            if (currentUrl) {
                const norm = this.normalizeLabelUrl(currentUrl);
                lab = labels.find(l => {
                    // 同时匹配 original_url (优先) 和 image_url (兼容旧数据或本地图)
                    return this.normalizeLabelUrl(l.original_url) === norm || 
                           this.normalizeLabelUrl(l.image_url) === norm;
                });
            }

            // 2. 尝试索引匹配 (Fallback)
            if (!lab) {
                // 情况 A: 标签对象自带 index 字段
                lab = labels.find(l => l.index === index);
                
                // 情况 B: 长度一致，直接按位置取 (Backend 注释说"与 image_list 同序")
                if (!lab && labels.length === imgList.length) {
                    lab = labels[index];
                }
            }
            
            // Debug Log: 如果有标签数据但找不到匹配，打印日志帮助排查
            if (labels.length > 0 && !lab) {
                console.log(`[LabelDebug] Mismatch for index ${index}:`);
                if (currentUrl) {
                    console.log(`  Current: ${currentUrl} -> ${this.normalizeLabelUrl(currentUrl)}`);
                }
                console.log(`  Candidates:`, labels.map(l => {
                    const u1 = l.original_url;
                    const u2 = l.image_url;
                    return `[${l.index}] Orig: ${u1} -> ${this.normalizeLabelUrl(u1)} | Img: ${u2} -> ${this.normalizeLabelUrl(u2)}`;
                }));
            }

            if (!lab) return '';
            const typeMap = { product_display: '主图', spec: '规格', material: '材质', other: '其他' };
            const t = typeMap[lab.image_type] || lab.image_type || '';
            const q = lab.quality_ok === true ? '✓' : (lab.quality_ok === false ? '✗' : '');
            return [t, q].filter(Boolean).join(' ');
        },
        getImageLabelTitle(goods, index) {
            const labels = goods && goods.carousel_labels && Array.isArray(goods.carousel_labels) ? goods.carousel_labels : [];
            const imgList = goods && goods.image_list && Array.isArray(goods.image_list) ? goods.image_list : [];
            
            let lab = null;
            const currentUrl = imgList[index];

            // 1. 尝试 URL 匹配
            if (currentUrl) {
                const norm = this.normalizeLabelUrl(currentUrl);
                lab = labels.find(l => {
                    return this.normalizeLabelUrl(l.original_url) === norm || 
                           this.normalizeLabelUrl(l.image_url) === norm;
                });
            }

            // 2. 尝试索引匹配 (Fallback)
            if (!lab) {
                lab = labels.find(l => l.index === index);
                if (!lab && labels.length === imgList.length) {
                    lab = labels[index];
                }
            }

            if (!lab) return '';
            const parts = [];
            if (lab.image_type) parts.push('类型: ' + lab.image_type);
            if (lab.shape && lab.shape !== 'unknown') parts.push('形状: ' + lab.shape);
            if (lab.design_desc) parts.push('描述: ' + lab.design_desc);
            if (typeof lab.quality_ok === 'boolean') parts.push('质量: ' + (lab.quality_ok ? '通过' : '不通过'));
            return parts.join(' | ');
        },
        // 获取原图URL（去掉缩略图参数）
        getOriginalUrl(url) {
            if (!url || typeof url !== 'string') return url;
            return url.split('?')[0];
        },
        // 全屏显示原图
        openFullscreenImage(url) {
            this.fullscreenImageUrl = this.getOriginalUrl(url);
            this.fullscreenImageVisible = true;
        },
        closeFullscreenImage() {
            this.fullscreenImageVisible = false;
            this.fullscreenImageUrl = '';
        },
        // ESC键处理：优先关闭全屏，否则退出图片选择状态
        handleKeyDown(event) {
            if (event.key === 'Escape') {
                if (this.fullscreenImageVisible) {
                    this.closeFullscreenImage();
                } else {
                    this.selectingImageMap = {};
                }
            }
        },
        // 点击文档处理，点击非目标区域退出选择状态
        handleDocumentClick(event) {
            // 检查是否点击在轮播图区域内
            const target = event.target;
            const isImageItem = target.closest('.all-images-item');
            const isScrollButton = target.closest('.scroll-buttons');
            const isActionButton = target.closest('.el-button'); // 排除操作按钮
            
            // 如果点击的不是轮播图区域、滚动按钮和操作按钮，清除所有选择状态
            if (!isImageItem && !isScrollButton && !isActionButton) {
                // 延迟执行，确保handleImageSelect先执行
                setTimeout(() => {
                    // 再次检查是否还有选择状态（如果handleImageSelect已经处理了，这里不应该清空）
                    // 这里我们只清空那些确实不在选择模式的状态
                    const hasActiveSelection = Object.values(this.selectingImageMap).some(mode => mode !== undefined && mode !== null);
                    if (!hasActiveSelection) {
                        this.selectingImageMap = {};
                    }
                }, 0);
            }
        },
        // 滚动到顶部
        scrollToTop() {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        },
        // 滚动到底部
        scrollToBottom() {
            window.scrollTo({
                top: document.documentElement.scrollHeight,
                behavior: 'smooth'
            });
        },
        // 滚动到第一条待上传商品
        async scrollToFirstPendingUpload() {
            try {
                // 获取第一个待上传商品的ID和排名
                const response = await axios.get(`${API_BASE_URL}/goods/first-pending-upload`);
                
                if (response.data.code === 0) {
                    const goodsId = response.data.data.id;
                    const rank = response.data.data.rank || 1;
                    const pageSize = this.pagination.page_size || 20;
                    
                    // 计算商品应该在哪一页（排名从1开始，所以是 (rank-1)/pageSize + 1）
                    const targetPage = Math.ceil(rank / pageSize);
                    
                    console.log(`[待上传定位] 商品ID: ${goodsId}, 排名: ${rank}, 目标页: ${targetPage}, 每页: ${pageSize}`);
                    
                    // 检查当前列表中是否有这个商品
                    const index = this.goodsList.findIndex(g => g.id === goodsId);
                    
                    if (index !== -1) {
                        // 如果当前列表中有，直接滚动到它
                        console.log(`[待上传定位] 商品在当前列表，位置: ${index}`);
                        await this.$nextTick();
                        const element = document.getElementById(`goods-card-${goodsId}`);
                        if (element) {
                            element.scrollIntoView({
                                behavior: 'smooth',
                                block: 'start'
                            });
                            // 高亮显示一下
                            element.style.transition = 'box-shadow 0.3s';
                            element.style.boxShadow = '0 0 20px rgba(103, 194, 58, 0.8)';
                            setTimeout(() => {
                                element.style.boxShadow = '';
                            }, 2000);
                            ElMessage.success('已定位到待上传商品');
                        }
                    } else {
                        // 如果当前列表中没有，需要跳转到目标页
                        console.log(`[待上传定位] 商品不在当前列表，跳转到第${targetPage}页`);
                        ElMessage.info(`正在跳转到第${targetPage}页...`);
                        
                        // 重置搜索条件，确保能找到商品
                        this.searchForm = { search: '', user_id: '' };
                        this.pagination.page = targetPage;
                        
                        // 加载目标页
                        await this.loadGoodsList();
                        
                        // 等待DOM更新后，再次检查并滚动
                        await this.$nextTick();
                        setTimeout(async () => {
                            const checkIndex = this.goodsList.findIndex(g => g.id === goodsId);
                            console.log(`[待上传定位] 目标页检查结果: ${checkIndex !== -1 ? '找到' : '未找到'}`);
                            
                            if (checkIndex !== -1) {
                                const element = document.getElementById(`goods-card-${goodsId}`);
                                if (element) {
                                    // 先滚动到顶部，确保商品可见
                                    window.scrollTo({
                                        top: 0,
                                        behavior: 'smooth'
                                    });
                                    
                                    // 等待滚动完成后再定位到商品
                                    setTimeout(() => {
                                        element.scrollIntoView({
                                            behavior: 'smooth',
                                            block: 'start'
                                        });
                                        element.style.transition = 'box-shadow 0.3s';
                                        element.style.boxShadow = '0 0 20px rgba(103, 194, 58, 0.8)';
                                        setTimeout(() => {
                                            element.style.boxShadow = '';
                                        }, 2000);
                                        ElMessage.success('已定位到待上传商品');
                                    }, 500);
                                }
                            } else {
                                // 如果目标页还是没有，可能是数据已更新或排名计算有误
                                // 尝试在所有页面中搜索
                                console.log(`[待上传定位] 目标页未找到，尝试全局搜索...`);
                                ElMessage.warning('商品不在目标页，尝试全局搜索...');
                                
                                // 从第1页开始逐页查找
                                let found = false;
                                const maxPages = Math.ceil(this.pagination.total / pageSize) || 10;
                                
                                for (let page = 1; page <= Math.min(maxPages, 20); page++) {
                                    this.pagination.page = page;
                                    await this.loadGoodsList();
                                    await this.$nextTick();
                                    
                                    const searchIndex = this.goodsList.findIndex(g => g.id === goodsId);
                                    if (searchIndex !== -1) {
                                        console.log(`[待上传定位] 在第${page}页找到商品`);
                                        found = true;
                                        const element = document.getElementById(`goods-card-${goodsId}`);
                                        if (element) {
                                            window.scrollTo({ top: 0, behavior: 'smooth' });
                                            setTimeout(() => {
                                                element.scrollIntoView({
                                                    behavior: 'smooth',
                                                    block: 'start'
                                                });
                                                element.style.transition = 'box-shadow 0.3s';
                                                element.style.boxShadow = '0 0 20px rgba(103, 194, 58, 0.8)';
                                                setTimeout(() => {
                                                    element.style.boxShadow = '';
                                                }, 2000);
                                                ElMessage.success(`已定位到待上传商品（第${page}页）`);
                                            }, 500);
                                        }
                                        break;
                                    }
                                    
                                    // 避免请求过快
                                    if (page < Math.min(maxPages, 20)) {
                                        await new Promise(resolve => setTimeout(resolve, 100));
                                    }
                                }
                                
                                if (!found) {
                                    console.log(`[待上传定位] 全局搜索未找到商品`);
                                    ElMessage.warning('未找到待上传商品，可能已被处理或状态已改变');
                                }
                            }
                        }, 300);
                    }
                } else {
                    ElMessage.warning('没有找到待上传的商品');
                }
            } catch (error) {
                console.error('滚动到待上传商品失败:', error);
                ElMessage.error('操作失败: ' + (error.message || '网络错误'));
            }
        },
        // 处理窗口大小变化
        handleResize() {
            const wasMobile = this.isMobile;
            this.isMobile = window.innerWidth <= 768;
            // 如果从桌面端切换到移动端，且搜索栏是展开的，则隐藏
            if (this.isMobile && !wasMobile && this.searchBarVisible) {
                this.searchBarVisible = false;
            }
            // 如果从移动端切换到桌面端，默认显示搜索栏
            if (!this.isMobile && wasMobile) {
                this.searchBarVisible = true;
            }
            // 更新主内容区域的顶部间距
            this.updateMainContentMargin();
        },
        // 切换搜索栏显示/隐藏
        toggleSearchBar() {
            this.searchBarVisible = !this.searchBarVisible;
            // 等待DOM更新后调整间距
            this.$nextTick(() => {
                this.updateMainContentMargin();
            });
        },
        // 更新主内容区域的顶部间距
        updateMainContentMargin() {
            const mainContent = document.querySelector('.main-content');
            if (!mainContent) return;
            
            const header = document.querySelector('.header');
            if (!header) return;
            
            // 计算header的实际高度
            const headerHeight = header.offsetHeight;
            
            // 设置主内容区域的顶部间距
            if (this.isMobile) {
                // 移动端：根据搜索栏是否显示调整间距
                mainContent.style.marginTop = this.searchBarVisible ? '200px' : '120px';
            } else {
                // 桌面端：根据搜索栏是否显示调整间距
                mainContent.style.marginTop = this.searchBarVisible ? '180px' : '120px';
            }
        }
    }
    });
    
    app.use(ElementPlus);
    
    // 确保#app元素存在
    const appElement = document.getElementById('app');
    if (!appElement) {
        console.error('未找到#app元素，无法挂载Vue应用');
        return;
    }
    
    app.mount('#app');
    console.log('Vue应用已成功挂载');
}

// 等待依赖加载完成后初始化
waitForDependencies(function() {
    // 确保DOM已加载
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initApp);
    } else {
        initApp();
    }
});

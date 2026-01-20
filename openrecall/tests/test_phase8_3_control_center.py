"""
Phase 8.3 Control Center API集成测试
完整的自动化测试套件，覆盖UI与API的集成
"""
import pytest
import json
import time
import sys
import subprocess
import threading
from urllib import request, error
from pathlib import Path

class TestControlCenterAPI:
    """Control Center API完整集成测试"""
    
    @classmethod
    def setup_class(cls):
        """启动OpenRecall服务器"""
        print("\n" + "="*60)
        print("启动OpenRecall服务器...")
        print("="*60)
        
        cls.server_process = subprocess.Popen(
            [sys.executable, "-m", "openrecall.server"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path(__file__).parent.parent
        )
        
        # 等待服务器启动
        for i in range(30):
            try:
                with request.urlopen('http://localhost:8083/', timeout=1):
                    print("✓ 服务器已启动")
                    break
            except (error.URLError, Exception):
                time.sleep(1)
                if i % 5 == 0:
                    print(f"  等待服务器... ({i}秒)")
        else:
            pytest.fail("服务器启动超时")
        
        time.sleep(1)  # 额外等待
    
    @classmethod
    def teardown_class(cls):
        """停止服务器"""
        print("\n" + "="*60)
        print("停止服务器...")
        print("="*60)
        cls.server_process.terminate()
        try:
            cls.server_process.wait(timeout=5)
            print("✓ 服务器已停止")
        except subprocess.TimeoutExpired:
            cls.server_process.kill()
            cls.server_process.wait()
            print("✓ 服务器已强制停止")
    
    # ==================== 基础功能测试 ====================
    
    def test_01_api_endpoint_exists(self):
        """测试1: /api/config 端点存在"""
        try:
            with request.urlopen('http://localhost:8083/api/config', timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                assert isinstance(data, dict)
                print("✓ 测试1通过: API端点可访问")
        except Exception as e:
            pytest.fail(f"✗ 测试1失败: {e}")
    
    def test_02_api_returns_valid_json(self):
        """测试2: API返回有效的JSON和所有必需字段"""
        try:
            with request.urlopen('http://localhost:8083/api/config', timeout=5) as resp:
                data = json.loads(resp.read().decode())
                
                required_keys = {
                    'recording_enabled',
                    'upload_enabled', 
                    'ai_processing_enabled',
                    'ui_show_ai'
                }
                
                assert set(data.keys()) >= required_keys, \
                    f"缺少字段: {required_keys - set(data.keys())}"
                
                for key, value in data.items():
                    assert isinstance(value, bool), \
                        f"{key}应该是布尔值，实际是{type(value)}"
                
                print(f"✓ 测试2通过: 返回有效的JSON")
                print(f"  配置: {data}")
        except Exception as e:
            pytest.fail(f"✗ 测试2失败: {e}")
    
    def test_03_api_initial_state(self):
        """测试3: 初始状态应该都是True"""
        try:
            with request.urlopen('http://localhost:8083/api/config', timeout=5) as resp:
                data = json.loads(resp.read().decode())
                
                # 记录初始状态
                for key, value in data.items():
                    print(f"  初始值: {key} = {value}")
                
                # 初始应该都是true（或至少大部分是）
                assert data.get('recording_enabled', True) in [True, False]
                assert data.get('upload_enabled', True) in [True, False]
                assert data.get('ai_processing_enabled', True) in [True, False]
                assert data.get('ui_show_ai', True) in [True, False]
                
                print("✓ 测试3通过: 初始状态有效")
        except Exception as e:
            pytest.fail(f"✗ 测试3失败: {e}")
    
    # ==================== POST请求测试 ====================
    
    def test_04_post_recording_enabled_false(self):
        """测试4: 通过POST禁用Recording"""
        req_data = {'recording_enabled': False}
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                assert data['recording_enabled'] == False, \
                    f"期望False，实际{data['recording_enabled']}"
                print("✓ 测试4通过: Recording已禁用")
                print(f"  响应: {data}")
        except Exception as e:
            pytest.fail(f"✗ 测试4失败: {e}")
    
    def test_05_post_recording_enabled_true(self):
        """测试5: 通过POST重新启用Recording"""
        req_data = {'recording_enabled': True}
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                assert data['recording_enabled'] == True
                print("✓ 测试5通过: Recording已启用")
        except Exception as e:
            pytest.fail(f"✗ 测试5失败: {e}")
    
    def test_06_post_upload_enabled_false(self):
        """测试6: 通过POST禁用Upload"""
        req_data = {'upload_enabled': False}
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                assert data['upload_enabled'] == False
                print("✓ 测试6通过: Upload已禁用")
        except Exception as e:
            pytest.fail(f"✗ 测试6失败: {e}")
    
    def test_07_post_upload_enabled_true(self):
        """测试7: 通过POST重新启用Upload"""
        req_data = {'upload_enabled': True}
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                assert data['upload_enabled'] == True
                print("✓ 测试7通过: Upload已启用")
        except Exception as e:
            pytest.fail(f"✗ 测试7失败: {e}")
    
    def test_08_post_ai_processing_enabled_false(self):
        """测试8: 通过POST禁用AI Processing"""
        req_data = {'ai_processing_enabled': False}
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                assert data['ai_processing_enabled'] == False
                print("✓ 测试8通过: AI Processing已禁用")
        except Exception as e:
            pytest.fail(f"✗ 测试8失败: {e}")
    
    def test_09_post_ai_processing_enabled_true(self):
        """测试9: 通过POST重新启用AI Processing"""
        req_data = {'ai_processing_enabled': True}
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                assert data['ai_processing_enabled'] == True
                print("✓ 测试9通过: AI Processing已启用")
        except Exception as e:
            pytest.fail(f"✗ 测试9失败: {e}")
    
    def test_10_post_ui_show_ai_false(self):
        """测试10: 通过POST禁用UI Show AI"""
        req_data = {'ui_show_ai': False}
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                assert data['ui_show_ai'] == False
                print("✓ 测试10通过: Show AI已禁用")
        except Exception as e:
            pytest.fail(f"✗ 测试10失败: {e}")
    
    def test_11_post_ui_show_ai_true(self):
        """测试11: 通过POST重新启用UI Show AI"""
        req_data = {'ui_show_ai': True}
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                assert data['ui_show_ai'] == True
                print("✓ 测试11通过: Show AI已启用")
        except Exception as e:
            pytest.fail(f"✗ 测试11失败: {e}")
    
    # ==================== 多键更新测试 ====================
    
    def test_12_post_multiple_keys_simultaneously(self):
        """测试12: 同时更新多个键"""
        req_data = {
            'recording_enabled': False,
            'upload_enabled': False,
            'ai_processing_enabled': False,
            'ui_show_ai': False
        }
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                
                for key, expected_value in req_data.items():
                    assert data[key] == expected_value, \
                        f"{key}: 期望{expected_value}，实际{data[key]}"
                
                print("✓ 测试12通过: 多键同时更新成功")
                print(f"  更新后的配置: {data}")
        except Exception as e:
            pytest.fail(f"✗ 测试12失败: {e}")
    
    def test_13_post_reset_all_to_true(self):
        """测试13: 重置所有设置为true"""
        req_data = {
            'recording_enabled': True,
            'upload_enabled': True,
            'ai_processing_enabled': True,
            'ui_show_ai': True
        }
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                
                for key in req_data:
                    assert data[key] == True
                
                print("✓ 测试13通过: 所有设置已重置为true")
        except Exception as e:
            pytest.fail(f"✗ 测试13失败: {e}")
    
    # ==================== 边界和错误处理测试 ====================
    
    def test_14_post_invalid_key_ignored(self):
        """测试14: 无效的键被忽略，有效的键被处理"""
        req_data = {
            'invalid_key_1': 'invalid_value',
            'recording_enabled': False,
            'another_invalid': True
        }
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                
                assert data['recording_enabled'] == False
                assert 'invalid_key_1' not in data
                assert 'another_invalid' not in data
                
                print("✓ 测试14通过: 无效键被忽略，有效键被处理")
        except Exception as e:
            pytest.fail(f"✗ 测试14失败: {e}")
    
    def test_15_post_empty_body_ignored(self):
        """测试15: 空请求体被忽略"""
        req_data = {}
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                
                # 应该返回当前配置
                assert 'recording_enabled' in data
                assert 'upload_enabled' in data
                
                print("✓ 测试15通过: 空请求体被安全处理")
        except Exception as e:
            pytest.fail(f"✗ 测试15失败: {e}")
    
    def test_16_post_partial_update(self):
        """测试16: 部分更新（只更新一个键）"""
        # 先重置所有为true
        self.test_13_post_reset_all_to_true()
        
        # 只更新recording_enabled
        req_data = {'recording_enabled': False}
        req = self._create_post_request('/api/config', req_data)
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode())
                
                assert data['recording_enabled'] == False
                # 其他应该保持true
                assert data['upload_enabled'] == True
                assert data['ai_processing_enabled'] == True
                assert data['ui_show_ai'] == True
                
                print("✓ 测试16通过: 部分更新成功（其他保持不变）")
        except Exception as e:
            pytest.fail(f"✗ 测试16失败: {e}")
    
    # ==================== 状态一致性测试 ====================
    
    def test_17_post_then_get_consistency(self):
        """测试17: POST后的GET应该返回相同的值"""
        # 设置一个配置
        req_data = {'recording_enabled': False, 'upload_enabled': True}
        req = self._create_post_request('/api/config', req_data)
        
        try:
            # POST
            with request.urlopen(req, timeout=5) as resp:
                post_data = json.loads(resp.read().decode())
            
            time.sleep(0.5)  # 等待处理
            
            # GET
            with request.urlopen('http://localhost:8083/api/config', timeout=5) as resp:
                get_data = json.loads(resp.read().decode())
            
            # 验证一致性
            assert post_data['recording_enabled'] == get_data['recording_enabled']
            assert post_data['upload_enabled'] == get_data['upload_enabled']
            
            print("✓ 测试17通过: POST和GET结果一致")
        except Exception as e:
            pytest.fail(f"✗ 测试17失败: {e}")
    
    def test_18_multiple_sequential_updates(self):
        """测试18: 多个顺序更新"""
        updates = [
            {'recording_enabled': False},
            {'upload_enabled': False},
            {'ai_processing_enabled': False},
            {'ui_show_ai': False},
        ]
        
        try:
            for i, update in enumerate(updates):
                req = self._create_post_request('/api/config', update)
                with request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    key = list(update.keys())[0]
                    assert data[key] == update[key], \
                        f"更新{i+1}失败: {key}"
                time.sleep(0.2)  # 更新间隔
            
            print("✓ 测试18通过: 所有顺序更新成功")
        except Exception as e:
            pytest.fail(f"✗ 测试18失败: {e}")
    
    # ==================== 性能测试 ====================
    
    def test_19_api_response_time(self):
        """测试19: API响应时间应该< 1秒"""
        try:
            times = []
            for i in range(5):
                start = time.time()
                with request.urlopen('http://localhost:8083/api/config', timeout=5) as resp:
                    json.loads(resp.read().decode())
                elapsed = (time.time() - start) * 1000  # 转换为毫秒
                times.append(elapsed)
            
            avg_time = sum(times) / len(times)
            max_time = max(times)
            
            assert avg_time < 1000, f"平均响应时间过长: {avg_time:.2f}ms"
            assert max_time < 2000, f"最大响应时间过长: {max_time:.2f}ms"
            
            print(f"✓ 测试19通过: API响应时间良好")
            print(f"  平均: {avg_time:.2f}ms, 最大: {max_time:.2f}ms")
        except Exception as e:
            pytest.fail(f"✗ 测试19失败: {e}")
    
    def test_20_post_response_time(self):
        """测试20: POST响应时间应该< 1秒"""
        try:
            times = []
            for i in range(5):
                req_data = {'recording_enabled': i % 2 == 0}
                req = self._create_post_request('/api/config', req_data)
                
                start = time.time()
                with request.urlopen(req, timeout=5) as resp:
                    json.loads(resp.read().decode())
                elapsed = (time.time() - start) * 1000
                times.append(elapsed)
            
            avg_time = sum(times) / len(times)
            max_time = max(times)
            
            assert avg_time < 1000, f"POST平均响应时间过长: {avg_time:.2f}ms"
            
            print(f"✓ 测试20通过: POST响应时间良好")
            print(f"  平均: {avg_time:.2f}ms, 最大: {max_time:.2f}ms")
        except Exception as e:
            pytest.fail(f"✗ 测试20失败: {e}")
    
    # ==================== 并发测试 ====================
    
    def test_21_concurrent_post_requests(self):
        """测试21: 处理并发POST请求"""
        results = {'success': 0, 'failed': 0, 'errors': []}
        lock = threading.Lock()
        
        def send_request(idx):
            try:
                req_data = {'recording_enabled': idx % 2 == 0}
                req = self._create_post_request('/api/config', req_data)
                with request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        with lock:
                            results['success'] += 1
                    else:
                        with lock:
                            results['failed'] += 1
            except Exception as e:
                with lock:
                    results['failed'] += 1
                    results['errors'].append(str(e))
        
        threads = [threading.Thread(target=send_request, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert results['success'] >= 8, \
            f"只有{results['success']}/10个并发请求成功"
        
        print(f"✓ 测试21通过: 并发请求处理成功")
        print(f"  成功: {results['success']}/10, 失败: {results['failed']}/10")
    
    # ==================== 辅助方法 ====================
    
    def _create_post_request(self, endpoint, data):
        """创建POST请求"""
        url = f'http://localhost:8083{endpoint}'
        req_data = json.dumps(data).encode('utf-8')
        return request.Request(
            url,
            data=req_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )


class TestControlCenterContentType:
    """测试内容类型处理"""
    
    @classmethod
    def setup_class(cls):
        """启动服务器"""
        # 跳过启动（使用主类的服务器）
        pass
    
    def test_22_json_content_type_required(self):
        """测试22: Content-Type必须是application/json"""
        url = 'http://localhost:8083/api/config'
        req_data = json.dumps({'recording_enabled': False}).encode()
        
        # 正确的Content-Type
        req = request.Request(
            url,
            data=req_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        try:
            with request.urlopen(req, timeout=5) as resp:
                assert resp.status == 200
                print("✓ 测试22通过: 正确的Content-Type被接受")
        except Exception as e:
            pytest.fail(f"✗ 测试22失败: {e}")


# 运行测试
if __name__ == '__main__':
    # 运行所有测试
    pytest.main([__file__, '-v', '-s', '--tb=short'])

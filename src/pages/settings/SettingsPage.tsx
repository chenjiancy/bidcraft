import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Modal,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from 'antd'
import { MoonOutlined, SunOutlined } from '@ant-design/icons'
import { useAppStore } from '../../stores/useAppStore'
import {
  confirmExternal,
  getExternalConfirmed,
  getModelConfig,
  getApiKey,
  hasApiKey,
  setApiKey,
  testConnection,
  updateModelConfig,
} from '../../api/modelConfig'

const { Title, Text } = Typography

/** 供应商预设（base_url 自动填充，用户可修改） */
const PROVIDER_PRESETS: Record<string, string> = {
  openai: 'https://api.openai.com',
  deepseek: 'https://api.deepseek.com',
  qwen: 'https://dashscope.aliyuncs.com/compatible-mode',
  ollama: 'http://localhost:11434',
  custom: '',
}

interface ConfigFormValues {
  provider: string
  base_url: string
  model: string
}

export default function SettingsPage() {
  const themeMode = useAppStore((s) => s.themeMode)
  const setThemeMode = useAppStore((s) => s.setThemeMode)

  const [configForm] = Form.useForm<ConfigFormValues>()
  const [configLoading, setConfigLoading] = useState(false)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [apiKeyExists, setApiKeyExists] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<null | {
    success: boolean
    response_text: string
    tokens_in: number | null
    tokens_out: number | null
    duration_ms: number
    error: string | null
  }>(null)
  const [externalConfirmed, setExternalConfirmed] = useState(false)
  const [externalModalOpen, setExternalModalOpen] = useState(false)
  const [pendingTest, setPendingTest] = useState(false)

  /** 加载模型配置 + API Key 状态 + 外联确认状态 */
  async function loadAll() {
    try {
      const [config, keyExists, extConfirmed] = await Promise.all([
        getModelConfig(),
        hasApiKey(),
        getExternalConfirmed(),
      ])
      configForm.setFieldsValue({
        provider: config.provider ?? 'openai',
        base_url: config.base_url ?? PROVIDER_PRESETS.openai,
        model: config.model ?? '',
      })
      setApiKeyExists(keyExists)
      setExternalConfirmed(extConfirmed.confirmed)
    } catch {
      message.error('加载模型配置失败')
    }
  }

  useEffect(() => {
    // 数据加载是 effect 的合理用途，setState 在异步回调中触发
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /** 供应商切换时自动填充 base_url */
  function handleProviderChange(provider: string) {
    const preset = PROVIDER_PRESETS[provider] ?? ''
    configForm.setFieldValue('base_url', preset)
  }

  /** 保存模型配置（不含 API Key） */
  async function handleSaveConfig() {
    try {
      const values = await configForm.validateFields()
      setConfigLoading(true)
      await updateModelConfig(values)
      message.success('模型配置已保存')
    } catch {
      message.error('保存失败')
    } finally {
      setConfigLoading(false)
    }
  }

  /** 保存 API Key（DPAPI 加密） */
  async function handleSaveApiKey() {
    if (!apiKeyInput) {
      message.warning('请输入 API Key')
      return
    }
    try {
      await setApiKey(apiKeyInput)
      setApiKeyExists(true)
      setApiKeyInput('')
      message.success('API Key 已加密保存')
    } catch {
      message.error('API Key 保存失败')
    }
  }

  /** 测试连接（含首次外联提示 NFR-3） */
  async function handleTestConnection() {
    if (!externalConfirmed) {
      setPendingTest(true)
      setExternalModalOpen(true)
      return
    }
    await doTestConnection()
  }

  async function doTestConnection() {
    try {
      const values = await configForm.validateFields()
      const apiKey = await getApiKey()
      if (!apiKey) {
        message.warning('请先保存 API Key')
        return
      }
      setTesting(true)
      setTestResult(null)
      const result = await testConnection({ ...values, api_key: apiKey })
      setTestResult(result)
      if (result.success) {
        message.success('连接成功')
      } else {
        message.error(`连接失败: ${result.error}`)
      }
    } catch {
      message.error('测试连接失败')
    } finally {
      setTesting(false)
    }
  }

  /** 用户确认首次外联 */
  async function handleExternalConfirm() {
    setExternalModalOpen(false)
    try {
      await confirmExternal()
      setExternalConfirmed(true)
      if (pendingTest) {
        setPendingTest(false)
        await doTestConnection()
      }
    } catch {
      message.error('确认失败')
    }
  }

  return (
    <Space direction="vertical" size="middle" className="w-full">
      <Card>
        <Title level={5}>外观</Title>
        <Descriptions column={1}>
          <Descriptions.Item label="主题模式">
            <Segmented
              value={themeMode}
              onChange={(value) => setThemeMode(value as 'light' | 'dark')}
              options={[
                { value: 'light', label: '亮色', icon: <SunOutlined /> },
                { value: 'dark', label: '暗色', icon: <MoonOutlined /> },
              ]}
            />
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card>
        <Title level={5}>模型配置</Title>
        <Text type="secondary">配置云端模型用于解析辅助（LLM 默认关闭，按需开启）</Text>

        <Form
          form={configForm}
          layout="vertical"
          initialValues={{ provider: 'openai' }}
          style={{ marginTop: 16 }}
        >
          <Form.Item label="供应商" name="provider" rules={[{ required: true }]}>
            <Select
              onChange={handleProviderChange}
              options={[
                { value: 'openai', label: 'OpenAI' },
                { value: 'deepseek', label: 'DeepSeek' },
                { value: 'qwen', label: '通义千问（阿里云）' },
                { value: 'ollama', label: 'Ollama（本地，预留）' },
                { value: 'custom', label: '自定义' },
              ]}
            />
          </Form.Item>

          <Form.Item label="Base URL" name="base_url" rules={[{ required: true }]}>
            <Input placeholder="https://api.example.com" />
          </Form.Item>

          <Form.Item label="模型名称" name="model" rules={[{ required: true }]}>
            <Input placeholder="如 gpt-4o / deepseek-chat / qwen-plus" />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" loading={configLoading} onClick={handleSaveConfig}>
                保存配置
              </Button>
              <Button loading={testing} onClick={handleTestConnection}>
                测试连接
              </Button>
            </Space>
          </Form.Item>
        </Form>

        {/* API Key（DPAPI 加密存储） */}
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <Text>API Key：</Text>
            {apiKeyExists ? (
              <Tag color="green">已设置（DPAPI 加密）</Tag>
            ) : (
              <Tag color="orange">未设置</Tag>
            )}
          </Space>
          <Space>
            <Input.Password
              placeholder={apiKeyExists ? '已保存，输入新值可覆盖' : '输入 API Key'}
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              style={{ width: 400 }}
            />
            <Button onClick={handleSaveApiKey}>保存 Key</Button>
          </Space>
          <Text type="secondary">API Key 经 Windows DPAPI 加密存储，不写入配置文件或日志</Text>
        </Space>

        {/* 测试连接结果 */}
        {testResult && (
          <Alert
            style={{ marginTop: 16 }}
            type={testResult.success ? 'success' : 'error'}
            showIcon
            message={testResult.success ? '连接成功' : '连接失败'}
            description={
              testResult.success ? (
                <Space direction="vertical">
                  <Text>响应：{testResult.response_text}</Text>
                  <Text type="secondary">
                    tokens_in={testResult.tokens_in ?? '-'} / tokens_out=
                    {testResult.tokens_out ?? '-'} / 耗时={testResult.duration_ms}ms
                  </Text>
                </Space>
              ) : (
                <Text>{testResult.error}</Text>
              )
            }
          />
        )}
      </Card>

      <Card>
        <Title level={5}>系统配置（占位）</Title>
        <Descriptions column={1}>
          <Descriptions.Item label="回收站清理">
            回收站保留时长配置将在 Task 21 完善（默认 30 天）
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 首次外联提示（NFR-3） */}
      <Modal
        title="首次外联提示"
        open={externalModalOpen}
        onOk={handleExternalConfirm}
        onCancel={() => {
          setExternalModalOpen(false)
          setPendingTest(false)
        }}
        okText="确认并继续"
        cancelText="取消"
      >
        <Text>
          本操作将向云端模型 API 发起网络请求。你的 API Key 已通过 DPAPI
          加密存储，不会明文传输到配置文件或日志中。 确认继续？
        </Text>
      </Modal>
    </Space>
  )
}

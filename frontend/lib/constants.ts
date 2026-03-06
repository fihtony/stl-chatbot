/**
 * 作业状态常量
 * 统一管理所有状态字符串，避免硬编码
 */
export const JOB_STATUS = {
  COMPLETED: 'completed',
  ERROR: 'error',
  RUNNING: 'running',
  IDLE: 'idle',
} as const;

export type JobStatus = typeof JOB_STATUS[keyof typeof JOB_STATUS];

/**
 * 状态配置映射
 * 包含每个状态的显示文本和样式类
 */
export const STATUS_CONFIG = {
  [JOB_STATUS.COMPLETED]: {
    label: '✓ Success',
    color: 'text-green-600',
    dotColor: 'bg-green-500',
  },
  [JOB_STATUS.ERROR]: {
    label: '✗ Failed',
    color: 'text-red-600',
    dotColor: 'bg-red-500',
  },
  [JOB_STATUS.RUNNING]: {
    label: 'Running...',
    color: 'text-blue-600',
    dotColor: 'bg-blue-500',
  },
  [JOB_STATUS.IDLE]: {
    label: 'Not run yet',
    color: 'text-gray-400 italic',
    dotColor: 'bg-gray-400',
  },
} as const;

/**
 * 获取状态显示信息
 */
export function getStatusDisplay(status: JobStatus | null | undefined) {
  if (!status) {
    return STATUS_CONFIG[JOB_STATUS.IDLE];
  }
  return STATUS_CONFIG[status] || STATUS_CONFIG[JOB_STATUS.IDLE];
}

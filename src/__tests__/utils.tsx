import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { useAppStore } from '../stores/useAppStore'

/** 重置 store 到初始状态（测试隔离）。 */
export function resetAppStore() {
  useAppStore.setState({
    themeMode: 'light',
    isParseConfirmed: false,
  })
}

/** 以指定路由渲染完整 App。 */
export function renderApp(route = '/') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>,
  )
}

const TOKEN_KEY = 'interview_auth_token'
const USERNAME_KEY = 'interview_auth_username'

export function saveAuth(token, username) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USERNAME_KEY, username)
  localStorage.removeItem('token')
  localStorage.removeItem('username')
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USERNAME_KEY)
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  localStorage.removeItem('interviewConfig')
  sessionStorage.removeItem('resumeData')
  sessionStorage.removeItem('selectedRole')
  sessionStorage.removeItem('assistant_pending')
  sessionStorage.removeItem('assistant_kb_question')
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function getUsername() {
  return localStorage.getItem(USERNAME_KEY) || ''
}

// 解析 JWT payload (无需第三方库, 只做本地过期检查; 真实校验由后端完成)
function _decodeJwtPayload(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const json = decodeURIComponent(
      atob(base64)
        .split('')
        .map(c => '%' + c.charCodeAt(0).toString(16).padStart(2, '0'))
        .join('')
    )
    return JSON.parse(json)
  } catch (_) {
    return null
  }
}

export function isAuthenticated() {
  const token = getToken()
  const username = getUsername()
  if (!token || !username) return false
  const payload = _decodeJwtPayload(token)
  if (!payload || payload.username !== username) return false
  // exp 为秒级时间戳; 过期 token 视为未登录, 路由守卫会送回登录页
  return typeof payload.exp === 'number' && payload.exp * 1000 > Date.now()
}

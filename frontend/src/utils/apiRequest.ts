import { getToken } from './serviceToken';

export const apiRequest = async (
  endpoint: string,
  method = "POST",
  body?: object | FormData,
  authRequired = false
) => {
  try {
    const headers: Record<string, string> = {};
    
    if (authRequired) {
      const token = getToken();
      if (!token) throw new Error("Требуется авторизация");
      headers.Authorization = `Bearer ${token}`;
    }
    
    const options: RequestInit = {
      method,
      headers,
    };
    
    if (body) {
      if (body instanceof FormData) {
        // For FormData, don't set Content-Type header (browser will set it)
        options.body = body;
      } else if (["POST", "PUT", "PATCH"].includes(method)) {
        // For JSON data
        headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(body);
      }
    }
    
    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/api/v1/${endpoint}`,
      options
    );
    
    if (!response.ok) {
      let errorBody: { detail?: string } | null = null;
      try {
        errorBody = await response.json();
      } catch {
        errorBody = null;
      }
      return {
        error: true,
        status: response.status,
        detail: errorBody?.detail || "Ошибка запроса",
      };
    }
    
    return response.json();
  } catch (error) {
    console.error(`Ошибка запроса (${endpoint}):`, error);
    return { error: true, status: null };
  }
};

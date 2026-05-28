import axios from "axios";

export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const msg = error?.response?.data?.detail
      || error?.message
      || "Неизвестная ошибка";
    console.error("[API Error]", msg, error);
    return Promise.reject(error);
  }
);
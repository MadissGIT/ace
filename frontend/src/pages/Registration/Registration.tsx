import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import styles from './Registration.module.scss';
import { apiRequest } from '../../utils/apiRequest.ts';
import { saveToken, setAuthHeader } from '../../utils/serviceToken.ts';
import axios from 'axios';
import { ArrowLeft, Eye, EyeOff } from 'lucide-react';

type VerificationProvider = 'max' | 'vk';

const Registration: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [formData, setFormData] = useState({
    fullName: '',
    email: '',
    phone: '',
    birth_date: '',
    password: '',
    sex: '' as string,
    region_id: null as number | null,
    confirmPassword: '',
  });

  const [sexOptions, setSexOptions] = useState<{ id: number; name: string }[]>([]);
  const [regionOptions, setRegionOptions] = useState<{ id: number; name: string }[]>([]);
  const [errors, setErrors] = useState({
    fullName: false,
    email: false,
    phone: false,
    password: false,
    sex: false,
    region_id: false,
    confirmPassword: false,
  });
  const [apiError, setApiError] = useState<string | null>(null);

  const [showPassword, setShowPassword] = useState({
    password: false,
    confirmPassword: false,
  });

  const [dateDisplay, setDateDisplay] = useState('');

  const [verificationProvider, setVerificationProvider] = useState<VerificationProvider>('max');
  const [maxRegistrationToken, setMaxRegistrationToken] = useState<string | null>(null);
  const [maxBotLink, setMaxBotLink] = useState<string | null>(null);
  const [maxVerified, setMaxVerified] = useState(false);
  const [maxVerifying, setMaxVerifying] = useState(false);
  const [vkRegistrationToken, setVkRegistrationToken] = useState<string | null>(null);
  const [vkVerified, setVkVerified] = useState(false);
  const [vkVerifying, setVkVerifying] = useState(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  useEffect(() => {
    return () => stopPolling();
  }, []);

  useEffect(() => {
    if (verificationProvider !== 'max' || !maxRegistrationToken || maxVerified) return;

    pollingRef.current = setInterval(async () => {
      try {
        const response = await apiRequest(
          `max/registration/status/${maxRegistrationToken}`,
          'GET',
          undefined,
          false
        );
        if (response?.verified) {
          setMaxVerified(true);
          setMaxVerifying(false);
          stopPolling();
        }
      } catch {
        // продолжаем polling при ошибке
      }
    }, 3000);

    return () => stopPolling();
  }, [verificationProvider, maxRegistrationToken, maxVerified]);

  const toggleShowPassword = (field: 'password' | 'confirmPassword') => () => {
    setShowPassword(prev => ({ ...prev, [field]: !prev[field] }));
  };

  const resetFormAndErrors = () => {
    setFormData({
      fullName: '',
      email: '',
      phone: '',
      birth_date: '',
      password: '',
      sex: '',
      region_id: null,
      confirmPassword: '',
    });
    setErrors({
      fullName: false,
      email: false,
      phone: false,
      password: false,
      sex: false,
      region_id: false,
      confirmPassword: false,
    });
    setApiError(null);
    setDateDisplay('');
    setMaxRegistrationToken(null);
    setMaxBotLink(null);
    setMaxVerified(false);
    setMaxVerifying(false);
    setVerificationProvider('max');
    setVkRegistrationToken(null);
    setVkVerified(false);
    setVkVerifying(false);
    stopPolling();
  };

  useEffect(() => {
    setTimeout(() => {
      if (document.activeElement instanceof HTMLElement) {
        document.activeElement.blur();
      }
    }, 100);
  }, []);

  useEffect(() => {
    return () => {
      resetFormAndErrors();
    };
  }, []);

  useEffect(() => {
    resetFormAndErrors();
  }, []);

  useEffect(() => {
    const vkToken = searchParams.get('vk_registration_token');
    const vkStatus = searchParams.get('vk_status');
    const vkError = searchParams.get('vk_error');

    if (vkToken && vkStatus === 'verified') {
      setVerificationProvider('vk');
      setVkRegistrationToken(vkToken);
      setVkVerified(true);
      setVkVerifying(false);
      setMaxRegistrationToken(null);
      setMaxBotLink(null);
      setMaxVerified(false);
      setMaxVerifying(false);
      stopPolling();
      setApiError(null);
      setSearchParams({}, { replace: true });
      const saved = sessionStorage.getItem('vk_registration_form');
      if (saved) {
        try {
          const { formData: savedFormData, dateDisplay: savedDateDisplay } = JSON.parse(saved);
          setFormData(savedFormData);
          setDateDisplay(savedDateDisplay);
        } catch {}
        sessionStorage.removeItem('vk_registration_form');
      }
    } else if (vkError) {
      setVerificationProvider('vk');
      setVkRegistrationToken(null);
      setVkVerified(false);
      setVkVerifying(false);
      setApiError(vkError);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const handleBackClick = () => {
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
    document.body.style.zoom = '1';
    resetFormAndErrors();
    navigate('/');
  };

  useEffect(() => {
    const fetchSexOptions = async () => {
      try {
        const response = await apiRequest('sex/', 'GET', undefined, false);
        if (response && response.data) {
          const filteredSexOptions = response.data.filter(
            (sex: { shortname: string }) => sex.shortname !== 'mixed'
          );
          setSexOptions(filteredSexOptions);
        }
      } catch (error) {
        console.error('Ошибка при загрузке данных о полах:', error);
      }
    };

    const fetchRegions = async () => {
      try {
        const response = await apiRequest('regions/', 'GET', undefined, false);
        if (response && response.data) {
          setRegionOptions(response.data);
        }
      } catch (error) {
        console.error('Ошибка при загрузке данных о регионах:', error);
      }
    };

    fetchSexOptions();
    fetchRegions();
  }, []);

  useEffect(() => {
    validateField('email', formData.email);
  }, [formData.email]);

  useEffect(() => {
    validateField('phone', formData.phone);
  }, [formData.phone]);

  useEffect(() => {
    validateField('password', formData.password);
  }, [formData.password]);

  useEffect(() => {
    validateField('confirmPassword', formData.confirmPassword);
  }, [formData.confirmPassword, formData.password]);

const validateField = (fieldName: string, value: string | number | null) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const phoneRegex = /^\+?\d{10,}$/;
    const passwordRegex = /^.{8,}$/;
    setErrors((prev) => ({
      ...prev,
      [fieldName]: fieldName === 'email'
        ? value !== '' && !emailRegex.test(value as string)
        : fieldName === 'phone'
          ? value !== '' && !phoneRegex.test((value as string).replace(/\D/g, ''))
          : fieldName === 'password'
            ? value !== '' && !passwordRegex.test(value as string)
            : fieldName === 'confirmPassword'
              ? value !== '' && value !== formData.password
              : false,
    }));
  };

  const validateFullName = () => {
    const words = formData.fullName.trim().split(/\s+/);
    const hasError = words.length !== 3;
    setErrors((prev) => ({ ...prev, fullName: hasError }));
    return !hasError;
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;

    if (name === 'phone') {
      let cleanedValue = value.replace(/\D/g, '');
      if (cleanedValue.length > 0 && !cleanedValue.startsWith('7')) {
        cleanedValue = '7' + cleanedValue;
      }
      setFormData((prev) => ({ ...prev, [name]: `+7 ${cleanedValue.slice(1)}` }));
    } else if (name === 'region_id') {
      const parsedValue = value === '' ? null : parseInt(value, 10);
      setFormData((prev) => ({ ...prev, [name]: parsedValue }));
    } else {
      setFormData((prev) => ({ ...prev, [name]: value }));
    }
  };

  const handleDateInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const digits = e.target.value.replace(/\D/g, '').slice(0, 8);
    let formatted = digits;
    if (digits.length > 4) {
      formatted = `${digits.slice(0, 2)}.${digits.slice(2, 4)}.${digits.slice(4)}`;
    } else if (digits.length > 2) {
      formatted = `${digits.slice(0, 2)}.${digits.slice(2)}`;
    }
    setDateDisplay(formatted);

    if (digits.length === 8) {
      const isoDate = `${digits.slice(4)}-${digits.slice(2, 4)}-${digits.slice(0, 2)}`;
      setFormData(prev => ({ ...prev, birth_date: isoDate }));
    } else {
      setFormData(prev => ({ ...prev, birth_date: '' }));
    }
  };

  const validateForm = () => {
    const emailValid = !errors.email && formData.email !== '';
    const phoneValid = !errors.phone && formData.phone !== '';
    const passwordValid = !errors.password && formData.password !== '';
    const confirmPasswordValid = !errors.confirmPassword && formData.confirmPassword !== '' && formData.confirmPassword === formData.password;
    const sexValid = formData.sex !== '';
    const regionValid = formData.region_id !== null;
    return validateFullName() && emailValid && phoneValid && passwordValid && confirmPasswordValid && sexValid && regionValid;
  };

  const identityVerified = verificationProvider === 'max' ? maxVerified : vkVerified;

  const selectVerificationProvider = (provider: VerificationProvider) => {
    setVerificationProvider(provider);
    setApiError(null);

    if (provider === 'max') {
      setVkRegistrationToken(null);
      setVkVerified(false);
      setVkVerifying(false);
    } else {
      setMaxRegistrationToken(null);
      setMaxBotLink(null);
      setMaxVerified(false);
      setMaxVerifying(false);
      stopPolling();
    }
  };

  const initiateMaxVerification = async () => {
    if (!formData.phone) return;
    selectVerificationProvider('max');
    setApiError(null);
    setMaxVerifying(true);

    try {
      const phone = formData.phone.replace(/\D/g, '');
      const response = await apiRequest('max/registration/session', 'POST', { phone_number: phone }, false);
      if (response?.error) {
        setApiError(response.detail || 'Не удалось создать сессию MAX. Попробуйте снова.');
        setMaxVerifying(false);
        return;
      }
      if (response?.registration_token && response?.bot_link) {
        setMaxRegistrationToken(response.registration_token);
        setMaxBotLink(response.bot_link);
      } else {
        setApiError('Не удалось создать сессию MAX. Попробуйте снова.');
        setMaxVerifying(false);
      }
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        setApiError(error.response.data.detail);
      } else {
        setApiError('Ошибка при инициализации MAX верификации.');
      }
      setMaxVerifying(false);
    }
  };

  const initiateVkVerification = async () => {
    if (!formData.phone) return;
    selectVerificationProvider('vk');
    setApiError(null);
    setVkVerifying(true);

    try {
      const phone = formData.phone.replace(/\D/g, '');
      const response = await apiRequest('vk/registration/session', 'POST', { phone_number: phone }, false);
      if (response?.error) {
        setApiError(response.detail || 'Не удалось создать сессию VK. Попробуйте снова.');
        setVkVerifying(false);
        return;
      }
      if (response?.authorization_url) {
        sessionStorage.setItem('vk_registration_form', JSON.stringify({ formData, dateDisplay }));
        window.location.href = response.authorization_url;
        return;
      }
      setApiError('Не удалось создать сессию VK. Попробуйте снова.');
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        setApiError(error.response.data.detail);
      } else {
        setApiError('Ошибка при инициализации VK верификации.');
      }
    }
    setVkVerifying(false);
  };

  const registerUser = async () => {
    if (verificationProvider === 'max' && !maxRegistrationToken) return;
    if (verificationProvider === 'vk' && !vkRegistrationToken) return;

    const [surname, name, patronymic] = formData.fullName.split(' ');
    const selectedSex = sexOptions.find((sex) => sex.name === formData.sex);
    const sex_id = selectedSex ? selectedSex.id : null;

    const userData = {
      email: formData.email,
      password: formData.password,
      name,
      surname,
      patronymic,
      phone_number: formData.phone.replace(/\D/g, ''),
      birth_date: formData.birth_date,
      sex_id,
      region_id: formData.region_id,
      verification_provider: verificationProvider,
      max_registration_token: verificationProvider === 'max' ? maxRegistrationToken : null,
      vk_registration_token: verificationProvider === 'vk' ? vkRegistrationToken : null,
    };

    try {
      const response = await apiRequest('users/signup', 'POST', userData, false);
      if (response && !response.error) {
        await login(userData.email, userData.password);
      } else {
        setApiError(response?.detail || 'Произошла ошибка при регистрации. Попробуйте снова.');
      }
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        setApiError(error.response.data.detail);
      } else {
        setApiError('Произошла ошибка при регистрации. Попробуйте снова.');
      }
      console.error('Ошибка при регистрации:', error);
    }
  };

  const login = async (email: string, password: string) => {
    try {
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);

      const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/v1/login/access-token`, formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      const token = response.data.access_token;
      if (token) {
        saveToken(token);
        setAuthHeader(token);
        navigate('/');
      } else {
        console.error('Токен не получен');
      }
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        setApiError(error.response.data.detail);
      } else {
        setApiError('Ошибка авторизации. Проверьте данные и попробуйте снова.');
      }
      console.error('Ошибка авторизации:', error);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiError(null);
    if (!validateForm()) return;
    if (!identityVerified) {
      setApiError('Подтвердите личность перед регистрацией.');
      return;
    }
    await registerUser();
  };

const navigateToLogin = () => {
    navigate('/login');
  };

  return (
    <div className={styles.formContainer}>
      <form className={styles.form} onSubmit={handleSubmit}>
        <div className={styles.formHeader}>
          <div className={styles.formHeader__header}>
            <button onClick={handleBackClick} className={styles.homeButton}>
              <ArrowLeft color="#ffffff" size={18} />
            </button>
            <h1>Регистрация</h1>
          </div>
          <button type="button" className={styles.loginButton} onClick={navigateToLogin}>
            Уже есть аккаунт? <span className={styles.tologin}>Войти</span>
          </button>
        </div>

        {apiError && (
          <div className={styles.apiErrorMessage}>
            {apiError}
          </div>
        )}

        <div className={styles.formGroup}>
          <div className={styles.labelWrapper}>
            <label className={styles.label}>Введите Ф.И.О. игрока</label>
          </div>
          <input
            type="text"
            name="fullName"
            value={formData.fullName}
            onChange={handleChange}
            className={`${styles.input} ${errors.fullName ? styles.error : ''}`}
            placeholder="Иванов Иван Иванович"
          />
          {errors.fullName && <div className={styles.errorMessage}>Ф.И.О. должно содержать три слова</div>}
        </div>

        {[
          {
            label: 'Введите Email',
            name: 'email',
            type: 'email',
            placeholder: 'example@mail.ru',
            error: errors.email,
            errorMessage: 'Укажите корректный email',
          },
          {
            label: 'Телефон',
            name: 'phone',
            type: 'tel',
            placeholder: '+7 (999)-000-00-00',
            error: errors.phone,
            errorMessage: 'Укажите корректный номер телефона',
          },
          {
            label: 'Пароль',
            name: 'password',
            type: showPassword.password ? 'text' : 'password',
            placeholder: 'Придумайте пароль',
            error: errors.password,
            errorMessage: 'Пароль должен содержать минимум 8 символов',
            isPassword: true,
            showPassword: showPassword.password,
            toggleShow: () => toggleShowPassword('password'),
          },
          {
            label: 'Повторите пароль',
            name: 'confirmPassword',
            type: showPassword.confirmPassword ? 'text' : 'password',
            placeholder: 'Повторите пароль',
            error: errors.confirmPassword,
            errorMessage: 'Пароли не совпадают',
            isPassword: true,
            showPassword: showPassword.confirmPassword,
            toggleShow: () => toggleShowPassword('confirmPassword'),
          },
          {
            label: 'Дата рождения игрока',
            name: 'birth_date',
            type: 'date',
            placeholder: 'дд.мм.гггг',
            max: new Date().toISOString().split('T')[0],
          },
        ].map(({ label, name, type, placeholder, error, errorMessage }) => (
          <div key={name} className={styles.formGroup}>
            <div className={styles.labelWrapper}>
              <label className={styles.label}>{label}</label>
            </div>

            {type === 'date' ? (
              <div className={styles.dateInputWrapper}>
                <input
                  type="text"
                  value={dateDisplay}
                  onChange={handleDateInput}
                  className={`${styles.input} ${error ? styles.error : ''}`}
                  placeholder={placeholder || 'дд.мм.гггг'}
                  maxLength={10}
                  inputMode="numeric"
                />
              </div>
            ) : (
              <div className={styles.passwordWrapper}>
                <input
                  type={type}
                  name={name}
                  value={formData[name as keyof typeof formData] === null ? '' : formData[name as keyof typeof formData]?.toString()}
                  onChange={handleChange}
                  className={`${styles.input} ${error ? styles.error : ''}`}
                  placeholder={placeholder}
                />
                {(name === 'password' || name === 'confirmPassword') && (
                  <button
                    type="button"
                    className={styles.showPasswordButton}
                    onClick={toggleShowPassword(name === 'password' ? 'password' : 'confirmPassword')}
                  >
                    {showPassword[name === 'password' ? 'password' : 'confirmPassword'] ? (
                      <EyeOff size={18} />
                    ) : (
                      <Eye size={18} />
                    )}
                  </button>
                )}
              </div>
            )}

            {error && errorMessage && (
              <div className={styles.errorMessage}>{errorMessage}</div>
            )}
          </div>
        ))}

        <div className={styles.formGroup}>
          <div className={styles.labelWrapper}>
            <label className={styles.label}>Пол</label>
          </div>
          <select
            name="sex"
            value={formData.sex}
            onChange={handleChange}
            className={`${styles.input} ${errors.sex ? styles.error : ''}`}
          >
            <option value="">Выберите пол</option>
            {sexOptions.map((sex) => (
              <option key={sex.id} value={sex.name}>
                {sex.name}
              </option>
            ))}
          </select>
          {errors.sex && <div className={styles.errorMessage}>Пожалуйста, выберите пол</div>}
        </div>

        <div className={styles.formGroup}>
          <div className={styles.labelWrapper}>
            <label className={styles.label}>Регион</label>
          </div>
          <select
            name="region_id"
            value={formData.region_id || ''}
            onChange={handleChange}
            className={`${styles.input} ${errors.region_id ? styles.error : ''}`}
          >
            <option value="">Выберите регион</option>
            {regionOptions.map((region) => (
              <option key={region.id} value={region.id}>
                {region.name}
              </option>
            ))}
          </select>
          {errors.region_id && <div className={styles.errorMessage}>Пожалуйста, выберите регион</div>}
        </div>

        <div className={styles.formGroup}>
          <div className={styles.labelWrapper}>
            <label className={styles.label}>Подтверждение личности <span style={{ fontWeight: 300, color: '#888888' }}>(выберите предпочитаемый способ)</span></label>
          </div>

          <div className={styles.verificationTabs}>
            <button
              type="button"
              className={`${styles.verificationTab} ${verificationProvider === 'max' ? styles.active : ''}`}
              onClick={() => selectVerificationProvider('max')}
            >
              <img src="/maxicon.png" alt="MAX" className={styles.providerIcon} />
              MAX
            </button>
            <button
              type="button"
              className={`${styles.verificationTab} ${verificationProvider === 'vk' ? styles.active : ''}`}
              onClick={() => selectVerificationProvider('vk')}
            >
              <img src="/vkicon.png" alt="VK" className={styles.providerIcon} />
              VK
            </button>
          </div>

          {verificationProvider === 'max' && (
            <>
              {maxVerified ? (
                <div className={styles.verifiedMessage}>
                  MAX подтверждён
                </div>
              ) : maxBotLink ? (
                <div className={styles.verificationLinkWrapper}>
                  <a
                    href={maxBotLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.providerButton}
                  >
                    Открыть <img src="/maxicon.png" alt="MAX" className={styles.providerIcon} />
                  </a>
                  <p className={styles.providerHint}>Ожидание подтверждения...</p>
                </div>
              ) : (
                <button
                  type="button"
                  className={styles.providerButton}
                  onClick={initiateMaxVerification}
                  disabled={maxVerifying || !formData.phone || !!errors.phone}
                >
                  {maxVerifying ? (
                    'Создание сессии...'
                  ) : (
                    <>
                      Подтвердить через <img src="/maxicon.png" alt="MAX" className={styles.providerIcon} />
                    </>
                  )}
                </button>
              )}
            </>
          )}

          {verificationProvider === 'vk' && (
            <>
              {vkVerified ? (
                <div className={styles.verifiedMessage}>
                  VK подтверждён
                </div>
              ) : (
                <button
                  type="button"
                  className={`${styles.providerButton} ${styles.vkButton}`}
                  onClick={initiateVkVerification}
                  disabled={vkVerifying || !formData.phone || !!errors.phone}
                >
                  {vkVerifying ? (
                    'Переход в VK...'
                  ) : (
                    <>
                      Подтвердить через <img src="/vkicon.png" alt="VK" className={styles.providerIcon} />
                    </>
                  )}
                </button>
              )}
            </>
          )}
        </div>

        <button
          type="submit"
          className={styles.submitButton}
          disabled={
            errors.email ||
            errors.phone ||
            errors.password ||
            errors.sex ||
            errors.region_id ||
            !identityVerified
          }
        >
          Зарегистрироваться
        </button>

        <p className={styles.consentText}>
          Нажимая на кнопку, вы даете согласие на обработку персональных данных и соглашаетесь с
          политикой конфиденциальности.
        </p>
      </form>
    </div>
  );
};

export default Registration;

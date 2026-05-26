import React, { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiRequest } from '../../../../utils/apiRequest.ts';
import Header from '../../../../components/Header/Header.tsx';
import styles from './GroupStage.module.scss';
import tournamentStyles from '../../TournamentPage.module.scss';
import PlayoffStage from '../PlayoffStage/PlayoffStage';

// === API СТРУКТУРЫ ===
interface Participant {
  id: number;
  user_id: number;
  partner_id: number | null;
  confirmed?: boolean;
}

interface Group {
  id: number;
  number: number;
  name: string;
  tournament_id: number;
  created_at?: string;
}

interface GroupParticipantLink {
  id?: number;
  group_id: number;
  participant_id: number;
}

interface Match {
  id: number;
  group_id: number;
  participant1_id: number;
  participant2_id: number;
  score1: number | null;
  score2: number | null;
  played: boolean;
}

// === ВНУТРЕННИЕ СТРУКТУРЫ ===
interface Player {
  id: number;
  /** Фамилия(и) + очки игрока(ов) */
  displayName: string;
  /** Суммарные очки (для возможной сортировки) – сейчас не используется в таблице */
  totalScore: number;
}

interface PlayerWithStats extends Player {
  position: number | null;  // null = не определено (не все матчи сыграны)
  points: number;
  scored: number;
  conceded: number;
  scoreDiff: number;
  allMatchesPlayed: boolean;
  scores: Map<number, string>;
  matchIdMap: Map<number, number>;
  /** Для каждого соперника — id игрока, который в БД лежит как participant1_id матча.
   *  Нужно чтобы при сохранении счёта корректно мапить row/col на score1/score2. */
  matchParticipant1Map: Map<number, number>;
}

interface GroupWithTable {
  id: number;
  number: number;
  name: string;
  players: PlayerWithStats[];
}

interface EditingCell {
  groupId: number;
  matchId: number;
  player1: number;
  player2: number;
  participant1_id: number;
  participant2_id: number;
  rowIndex: number;
  colIndex: number;
}

type MainCountMode = 'per_group' | 'total';

const GroupStage: React.FC = () => {
  const { tournamentId } = useParams<{ tournamentId: string }>();
  const navigate = useNavigate();
  const [groups, setGroups] = useState<GroupWithTable[]>([]);
  const [loading, setLoading] = useState(true);
  const [isOrganizer, setIsOrganizer] = useState(false);
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // === ОЛИМПИЙСКАЯ СЕТКА ===
  const [showPlayoffModal, setShowPlayoffModal] = useState(false);
  const [mainCount, setMainCount] = useState(2);
  const [mainCountMode, setMainCountMode] = useState<MainCountMode>('per_group');
  const [additionalCount, setAdditionalCount] = useState(0);
  const [playoffLoading, setPlayoffLoading] = useState(false);
  const [playoffError, setPlayoffError] = useState<string | null>(null);

  const handleOpenPlayoffModal = () => {
    setMainCount(2);
    setMainCountMode('per_group');
    setAdditionalCount(0);
    setPlayoffError(null);
    setShowPlayoffModal(true);
  };

  const handleClosePlayoffModal = () => {
    setShowPlayoffModal(false);
    setPlayoffError(null);
  };

  const handleCreatePlayoff = async () => {
    if (!tournamentId) return;
    setPlayoffLoading(true);
    setPlayoffError(null);
    try {
      // Build query string for parameters
      const params = new URLSearchParams({
        tournament_id: String(tournamentId),
        main_count: String(mainCount),
        main_count_mode: mainCountMode,
        additional_count: String(additionalCount),
      });
      await apiRequest(
        `playoffs/create?${params.toString()}`,
        'POST',
        undefined,
        true
      );
      setShowPlayoffModal(false);
      setShowPlayoff(true);
      // Можно добавить редирект или обновление состояния
    } catch (e: any) {
      setPlayoffError(e?.detail || 'Ошибка создания олимпийской сетки');
      setShowPlayoff(false); // Не показываем PlayoffStage при ошибке
      // Не закрываем модалку, чтобы показать ошибку
    } finally {
      setPlayoffLoading(false);
    }
  };

  // === СОСТОЯНИЕ ДЛЯ PLAYOFF ===
  const [participantMap, setParticipantMap] = useState<{ [id: number]: { displayName: string; points?: number } }>({});
  const [showPlayoff, setShowPlayoff] = useState(false);
  const [playoffStageKey] = useState(0);

  // === ПРОВЕРКА РОЛИ ===
  const checkUserRole = async () => {
    if (!tournamentId) return;
    try {
      const user = await apiRequest('users/me', 'GET', undefined, true);
      const tournament = await apiRequest(`tournaments/${tournamentId}`, 'GET', undefined, false);
      setIsOrganizer(user?.id === tournament.owner_id);
      if (user?.id === 5) setIsOrganizer(true);
    } catch (error) {
      console.error('Ошибка проверки роли:', error);
      setIsOrganizer(false);
    }
  };

  // === 1. УЧАСТНИКИ + ПОЛЬЗОВАТЕЛИ ===
  const fetchParticipantsAndUsers = async (): Promise<Map<number, Player>> => {
    if (!tournamentId) return new Map();

    try {
      const resp = await apiRequest(`tournaments/${tournamentId}/participants`, 'GET', undefined, false);
      const participants: Participant[] = resp?.data ?? [];

      const userIds = new Set<number>();
      participants.forEach(p => {
        if (p.user_id) userIds.add(p.user_id);
        if (p.partner_id) userIds.add(p.partner_id);
      });

      const users = await Promise.all(
        Array.from(userIds).map(async (id) => {
          try {
            const user = await apiRequest(`users/${id}`, 'GET', undefined, false);
            return [id, user] as const;
          } catch {
            return [id, null] as const;
          }
        })
      );

      const usersMap = new Map(users.filter(([, u]) => u !== null));

      const playersMap = new Map<number, Player>();

      participants.forEach(p => {
        const mainUser = usersMap.get(p.user_id);
        if (!mainUser) return;

        const mainScore = Number(mainUser.score) || 0;
        let displayName = `${mainUser.surname || mainUser.name}`;
        let totalScore = mainScore;

        if (p.partner_id) {
          const partnerUser = usersMap.get(p.partner_id);
          if (partnerUser) {
            const partnerScore = Number(partnerUser.score) || 0;
            displayName = `${mainUser.surname}/${partnerUser.surname}`;
            totalScore += partnerScore;
          }
        }

        playersMap.set(p.id, {
          id: p.id,
          displayName,
          totalScore,
        });
      });

      return playersMap;
    } catch (e) {
      console.error('Ошибка загрузки участников:', e);
      return new Map();
    }
  };

  // === 2. ГРУППА — ПОДСЧЁТ ТАБЛИЦЫ ===
  const fetchGroupTable = async (
    group: Group,
    allPlayers: Map<number, Player>
  ): Promise<GroupWithTable> => {
    try {
      const linksResp = await apiRequest(`groups/${group.id}/participants`, 'GET', undefined, false);
      const links: GroupParticipantLink[] = Array.isArray(linksResp) ? linksResp : linksResp?.data ?? [];
      const orderedIds = links.map(l => l.participant_id);

      const groupPlayers = orderedIds
        .map(id => allPlayers.get(id))
        .filter((p): p is Player => p !== null);

      const matchesResp = await apiRequest(`groups/${group.id}/matches`, 'GET', undefined, false);
      const matches: Match[] = Array.isArray(matchesResp) ? matchesResp : matchesResp?.data ?? [];

      const stats = new Map<number, {
        player: Player;
        points: number;
        scored: number;
        conceded: number;
        scores: Map<number, string>;
        matchIdMap: Map<number, number>;
        matchParticipant1Map: Map<number, number>;
        playedMatches: number;
      }>();

      groupPlayers.forEach(p => {
        stats.set(p.id, {
          player: p,
          points: 0,
          scored: 0,
          conceded: 0,
          scores: new Map(),
          matchIdMap: new Map(),
          matchParticipant1Map: new Map(),
          playedMatches: 0,
        });
      });

      matches.forEach(m => {
        const p1 = m.participant1_id;
        const p2 = m.participant2_id;
        const s1 = m.score1;
        const s2 = m.score2;

        const stat1 = stats.get(p1);
        const stat2 = stats.get(p2);
        if (!stat1 || !stat2) return;

        const scoreStr = s1 != null && s2 != null ? `${s1}/${s2}` : '';
        stat1.scores.set(p2, scoreStr);
        stat1.matchIdMap.set(p2, m.id);
        stat1.matchParticipant1Map.set(p2, p1);

        stat2.scores.set(p1, s1 != null && s2 != null ? `${s2}/${s1}` : '');
        stat2.matchIdMap.set(p1, m.id);
        stat2.matchParticipant1Map.set(p1, p1);

        if (s1 != null && s2 != null) {
          stat1.playedMatches += 1;
          stat2.playedMatches += 1;

          stat1.scored += s1;
          stat1.conceded += s2;
          stat2.scored += s2;
          stat2.conceded += s1;

          if (s1 > s2) stat1.points += 1;
          else if (s1 < s2) stat2.points += 1;
        }
      });

      const totalMatchesPerPlayer = groupPlayers.length - 1;

      const extendedStats = groupPlayers.map(p => {
        const s = stats.get(p.id)!;
        const allMatchesPlayed = s.playedMatches === totalMatchesPerPlayer;
        const scoreDiff = s.scored - s.conceded;

        return {
          ...p,
          points: s.points,
          scored: s.scored,
          conceded: s.conceded,
          scoreDiff,
          allMatchesPlayed,
          scores: s.scores,
          matchIdMap: s.matchIdMap,
          matchParticipant1Map: s.matchParticipant1Map,
        };
      });

      // Сортировка: очки → разница → забитые → id
      const sorted = [...extendedStats].sort((a, b) =>
        b.points - a.points ||
        b.scoreDiff - a.scoreDiff ||
        b.scored - a.scored ||
        a.id - b.id
      );

      // Определяем места только для тех, кто сыграл все матчи
      const positionMap = new Map<number, number>();
      let currentPos = 1;

      for (const player of sorted) {
        if (player.allMatchesPlayed) {
          positionMap.set(player.id, currentPos++);
        } else {
          positionMap.set(player.id, 0);
        }
      }

      const finalPlayers: PlayerWithStats[] = extendedStats.map(p => ({
        ...p,
        position: positionMap.get(p.id) ?? null,
      }));

      return { ...group, players: finalPlayers };
    } catch (err) {
      console.error(`Группа ${group.id} ошибка:`, err);
      return { ...group, players: [] };
    }
  };

  // === 3. ПОЛНАЯ ЗАГРУЗКА ===
  const fetchGroups = async () => {
    if (!tournamentId) return;
    setLoading(true);

    try {
      const allPlayers = await fetchParticipantsAndUsers();
      const groupsResp = await apiRequest(`groups/tournament/${tournamentId}`, 'GET', undefined, false);
      const groups: Group[] = Array.isArray(groupsResp) ? groupsResp : groupsResp?.data ?? [];

      const tables = await Promise.all(groups.map(g => fetchGroupTable(g, allPlayers)));
      setGroups(tables);
    } catch (e) {
      console.error('Ошибка загрузки групп:', e);
      setGroups([]);
    } finally {
      setLoading(false);
    }
  };


  // === РЕДАКТИРОВАНИЕ ===
  const handleCellClick = (
    groupId: number,
    player1: PlayerWithStats,
    player2: PlayerWithStats,
    rowIndex: number,
    colIndex: number
  ) => {
    if (!isOrganizer) return;
    const matchId = player1.matchIdMap.get(player2.id);
    if (!matchId) return;
    // participant1_id матча известен из уже загруженных данных
    // (групповые матчи приходят в `groups/{group_id}/matches`).
    const participant1_id = player1.matchParticipant1Map.get(player2.id);
    if (participant1_id === undefined) return;
    const participant2_id = participant1_id === player1.id ? player2.id : player1.id;
    setEditingCell({
      groupId,
      matchId,
      player1: player1.id,
      player2: player2.id,
      participant1_id,
      participant2_id,
      rowIndex,
      colIndex,
    });
  };

  // === ОБРАБОТКА ВВОДА СЧЁТА ===
  const handleScoreSubmit = async (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    if (!editingCell) return;
    const value = (e.target as HTMLInputElement).value.trim();
    const [s1str, s2str] = value.split(/[/:\\-]/).map(s => s.trim());
    const s1 = parseInt(s1str, 10);
    const s2 = parseInt(s2str, 10);
    if (isNaN(s1) || isNaN(s2)) return;

    try {
      // В клетке (строка = player1, столбец = player2) пользователь вводит
      // "row_score / col_score". В БД score1 принадлежит participant1_id,
      // а participant1_id не обязательно совпадает с player1 (строкой) —
      // порядок зависит от того, как бэк создал матч.
      // Поэтому смотрим, кто из игроков реально лежит в participant1_id.
      let score1: number;
      let score2: number;
      if (editingCell.participant1_id === editingCell.player1) {
        // Игрок-строка лежит в participant1 → его счёт идёт в score1
        score1 = s1;
        score2 = s2;
      } else {
        // Игрок-строка лежит в participant2 → его счёт идёт в score2
        score1 = s2;
        score2 = s1;
      }
      await apiRequest(
        `groups/matches/${editingCell.matchId}`,
        'PUT',
        { score1, score2, played: true },
        true
      );
      await fetchGroups();
      setEditingCell(null);
    } catch (err) {
      console.error('Ошибка сохранения:', err);
    }
  };

  useEffect(() => {
    if (editingCell && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingCell]);

  useEffect(() => {
    checkUserRole();
    fetchGroups();
  }, [tournamentId]);

  useEffect(() => {
    fetchParticipantsAndUsers().then(map => {
      // преобразуем Map в объект для быстрого доступа
      const obj: { [id: number]: { displayName: string; points?: number } } = {};
      map.forEach((v, k) => {
        obj[k] = { displayName: v.displayName };
      });
      setParticipantMap(obj);
    });
  }, [tournamentId]);

  // === ПОКАЗЫВАТЬ PLAYOFF ЕСЛИ СУЩЕСТВУЕТ НА СЕРВЕРЕ ===
  useEffect(() => {
    if (!tournamentId) return;
    const fetchPlayoff = async () => {
      try {
        const data = await apiRequest(`playoffs/tournament/${tournamentId}`, 'GET');
        if (data && data.stage_id) setShowPlayoff(true);
      } catch {
        setShowPlayoff(false);
      }
    };
    fetchPlayoff();
    // Подписка на событие удаления олимпийской сетки
    const handler = () => setShowPlayoff(false);
    window.addEventListener('playoffDeleted', handler);
    return () => {
      window.removeEventListener('playoffDeleted', handler);
    };
  }, [tournamentId]);

  if (loading) {
    return (
      <div className={tournamentStyles.loaderContainer}>
        <div className={tournamentStyles.loader} />
        <p>Загрузка таблицы...</p>
      </div>
    );
  }

  if (groups.length === 0) {
    return (
      <div className={tournamentStyles.pageWrapper}>
        <Header scrollToBenefits={() => {}} />
        <main className={tournamentStyles.mainContent}>
          <div className={styles.tournamentContainer}>
            <div className={styles.contentWrapper}>
              <h1 className={tournamentStyles.tournamentName}>Группы</h1>
              <p className={styles.emptyMessage}>Группы не сформированы</p>
              {isOrganizer && (
                <button
                  onClick={() => navigate(`/tournaments/${tournamentId}/groupstage/setup`)}
                  className={styles.createGroupsBtn}
                >
                  Сформировать
                </button>
              )}
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className={tournamentStyles.pageWrapper}>
      <Header scrollToBenefits={() => {}} />
      <main className={tournamentStyles.mainContent}>
        <div className={styles.tournamentContainer}>
          <div className={styles.contentWrapper}>
            <div className={styles.headerRow}>
              <h1 className={tournamentStyles.tournamentName}>Турнирная таблица</h1>
              {isOrganizer && (
                <button
                  onClick={() => navigate(`/tournaments/${tournamentId}/groupstage/setup`)}
                  className={styles.editGroupsBtn}
                >
                  Редактировать
                </button>
              )}
            </div>
          </div>

          <div className={styles.tablesGrid}>
            {groups.map(group => (
              <div key={group.id} className={styles.tableWrapper}>
                <div className={styles.tableScroll}>
                  <table className={styles.groupTable}>
                    <thead>
                      <tr>
                        <th colSpan={2}>Гр. {group.number}</th>
                        {group.players.map((_, i) => <th key={i}>{i + 1}</th>)}
                        <th>Очки</th>
                        <th>Разница</th>
                        <th>Место</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.players.map((player, i) => (
                        <tr key={player.id}>
                          <td>{i + 1}</td>
                          <td className={styles.playerName}>{player.displayName}</td>
                          {group.players.map((opponent, j) => {
                            if (opponent.id === player.id) return <td key={opponent.id} className={styles.selfCell} />;
                            const score = player.scores.get(opponent.id) || '';
                            const matchId = player.matchIdMap.get(opponent.id);
                            const isEditing = editingCell?.groupId === group.id &&
                              editingCell?.matchId === matchId &&
                              editingCell?.player1 === player.id &&
                              editingCell?.player2 === opponent.id;

                            return (
                              <td
                                key={opponent.id}
                                className={isOrganizer ? styles.editableCell : ''}
                                onClick={() => handleCellClick(group.id, player, opponent, i, j)}
                              >
                                {isEditing ? (
                                  <input
                                    ref={inputRef}
                                    type="text"
                                    defaultValue={score}
                                    onKeyDown={handleScoreSubmit}
                                    onBlur={() => setEditingCell(null)}
                                    className={styles.scoreInput}
                                    placeholder="4/1"
                                    autoFocus
                                  />
                                ) : (
                                  score || '—'
                                )}
                              </td>
                            );
                          })}
                          <td>{player.points}</td>
                          <td>{player.scoreDiff >= 0 ? `+${player.scoreDiff}` : player.scoreDiff}</td>
                          <td>{player.position !== null ? player.position : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>


          {isOrganizer && (!showPlayoff || playoffError) && (
            <div style={{ marginTop: 32, textAlign: 'center' }}>
              <button
                className={styles.createPlayoffBtn}
                onClick={handleOpenPlayoffModal}
                disabled={showPlayoffModal}
              >
                Сформировать олимпийскую сетку
              </button>
            </div>
          )}

          {showPlayoffModal && (
            <div className={styles.modalOverlay}>
              <div className={styles.modalContent}>
                <h2>Сформировать олимпийскую сетку</h2>
                <div style={{ marginBottom: 16 }}>
                  <label>
                    Режим основной сетки:
                    <select
                      value={mainCountMode}
                      onChange={e => setMainCountMode(e.target.value as MainCountMode)}
                      style={{ marginLeft: 8 }}
                    >
                      <option value="per_group">До N мест из каждой группы</option>
                      <option value="total">N участников всего</option>
                    </select>
                  </label>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <label>
                    {mainCountMode === 'per_group' ? 'Мест из группы:' : 'Участников всего:'}
                    <input
                      type="number"
                      min={0}
                      value={mainCount}
                      onChange={e => setMainCount(Number(e.target.value))}
                      style={{ marginLeft: 8, width: 60 }}
                    />
                  </label>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <label>
                    Доп. сетка:
                    <input
                      type="number"
                      min={0}
                      value={additionalCount}
                      onChange={e => setAdditionalCount(Number(e.target.value))}
                      style={{ marginLeft: 8, width: 60 }}
                    />
                  </label>
                </div>
                {playoffError && (
                  <div style={{ color: 'red', marginBottom: 8, whiteSpace: 'pre-line', fontWeight: 500 }}>
                    {playoffError}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
                  <button onClick={handleCreatePlayoff} disabled={playoffLoading}>
                    {playoffLoading ? 'Создание...' : 'Создать'}
                  </button>
                  <button onClick={handleClosePlayoffModal} disabled={playoffLoading}>
                    Отмена
                  </button>
                </div>
              </div>
            </div>
          )}

          {showPlayoff && (
            <PlayoffStage
              key={playoffStageKey}
              tournamentId={tournamentId!}
              participantMap={participantMap}
              isOrganizer={isOrganizer}
            />
          )}
        </div>
      </main>
    </div>
  );
};

export default GroupStage;

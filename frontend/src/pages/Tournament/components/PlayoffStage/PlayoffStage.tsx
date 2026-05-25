import React, { useEffect, useState } from 'react';
import { apiRequest } from '../../../../utils/apiRequest';
import styles from './PlayoffStage.module.scss';

interface PlayoffMatch {
  match_id: number;
  participant1_id: number | null;
  participant2_id: number | null;
  score1: number | null;
  score2: number | null;
  winner_id: number | null;
  played: boolean;
  order?: number;
}

interface PlayoffRound {
  round_id: number;
  number: number;
  name: string;
  matches: PlayoffMatch[];
}

interface PlayoffBracket {
  bracket_id: number;
  type: string;
  rounds: PlayoffRound[];
}

interface PlayoffStageSchema {
  stage_id: number;
  brackets: PlayoffBracket[];
}

interface ParticipantMap {
  [id: number]: { displayName: string; points?: number };
}

interface PlayoffStageProps {
  tournamentId: number | string;
  participantMap: ParticipantMap;
  isOrganizer?: boolean;
}

const BASE_SLOT_HEIGHT = 160; // px — минимальный слот для одного матча

const COMPRESSED_16_PRELIMINARY_ROUTES = [
  { highSeed: 13, quarterfinalIndex: 1, targetSlot: 'participant1_id' },
  { highSeed: 12, quarterfinalIndex: 1, targetSlot: 'participant2_id' },
  { highSeed: 14, quarterfinalIndex: 2, targetSlot: 'participant1_id' },
  { highSeed: 11, quarterfinalIndex: 2, targetSlot: 'participant2_id' },
  { highSeed: 10, quarterfinalIndex: 3, targetSlot: 'participant2_id' },
  { highSeed: 15, quarterfinalIndex: 3, targetSlot: 'participant1_id' },
  { highSeed: 9, quarterfinalIndex: 0, targetSlot: 'participant2_id' },
];

const isCompressed16Bracket = (bracket: PlayoffBracket) => {
  const matchCounts = bracket.rounds.map(round => round.matches.length);
  return (
    matchCounts.length === 4 &&
    matchCounts[0] >= 1 &&
    matchCounts[0] <= 7 &&
    matchCounts[1] === 4 &&
    matchCounts[2] === 2 &&
    matchCounts[3] === 1
  );
};

const getCompressed16PreliminarySlotIndex = (matchIndex: number, preliminaryMatchCount: number) => {
  const routes = COMPRESSED_16_PRELIMINARY_ROUTES.filter(
    route => route.highSeed <= preliminaryMatchCount + 8
  );
  const route = routes[matchIndex];
  if (!route) return matchIndex;

  return route.quarterfinalIndex * 2 + (route.targetSlot === 'participant1_id' ? 0 : 1);
};

const PlayoffStage: React.FC<PlayoffStageProps> = ({ tournamentId, participantMap, isOrganizer }) => {
  const [stage, setStage] = useState<PlayoffStageSchema | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editScores, setEditScores] = useState<{ [matchId: number]: { score1: string; score2: string } }>({});
  const [editingMatchId, setEditingMatchId] = useState<number | null>(null);
  const [savingMatchId, setSavingMatchId] = useState<number | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const fetchStage = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest(`playoffs/tournament/${tournamentId}`, 'GET');
      setStage(data);
    } catch (e: any) {
      if (e?.status === 404 || e?.response?.status === 404) {
        setError('Олимпийская сетка не создана для этого турнира.');
      } else {
        setError(e?.detail || 'Ошибка загрузки олимпийской сетки');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStage();
  }, [tournamentId]);

  const handleSave = async (matchId: number) => {
    const { score1, score2 } = editScores[matchId] || { score1: '', score2: '' };
    if (score1 === '' || score2 === '') return;
    const s1 = parseInt(score1, 10);
    const s2 = parseInt(score2, 10);
    if (isNaN(s1) || isNaN(s2)) return;

    setSavingMatchId(matchId);
    try {
      await apiRequest(`playoffs/match/${matchId}/result`, 'POST', { score1: s1, score2: s2 }, true);
      await fetchStage();
      setEditScores(prev => {
        const copy = { ...prev };
        delete copy[matchId];
        return copy;
      });
      setEditingMatchId(null);
    } finally {
      setSavingMatchId(null);
    }
  };

  const handleStartEdit = (match: PlayoffMatch) => {
    setEditingMatchId(match.match_id);
    setEditScores(prev => ({
      ...prev,
      [match.match_id]: {
        score1: match.score1 !== null && match.score1 !== undefined ? String(match.score1) : '',
        score2: match.score2 !== null && match.score2 !== undefined ? String(match.score2) : '',
      },
    }));
  };

  const handleCancelEdit = (matchId: number) => {
    setEditingMatchId(null);
    setEditScores(prev => {
      const copy = { ...prev };
      delete copy[matchId];
      return copy;
    });
  };

  let canDelete = false;
  let stageId = stage?.stage_id;
  if (stage && isOrganizer) {
    // Пустую сетку (без bracket'ов или без матчей) удалять можно всегда
    const brackets = Array.isArray(stage.brackets) ? stage.brackets : [];
    if (brackets.length === 0) {
      canDelete = true;
    } else {
      const mainBracket = brackets.find(b => b.type === 'main') || brackets[0];
      if (!mainBracket || mainBracket.rounds.length === 0) {
        canDelete = true;
      } else {
        const finalRound = mainBracket.rounds[mainBracket.rounds.length - 1];
        if (!finalRound || finalRound.matches.length === 0) {
          canDelete = true;
        } else {
          canDelete = !finalRound.matches[0].played;
        }
      }
    }
  }

  const handleDeleteGrid = async () => {
    if (!stageId) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await apiRequest(`playoffs/stage/${stageId}`, 'DELETE', undefined, true);
      setStage(null);
      if (typeof window !== 'undefined' && window.dispatchEvent) {
        window.dispatchEvent(new CustomEvent('playoffDeleted'));
      }
    } catch (e: any) {
      setDeleteError(e?.detail || 'Ошибка удаления олимпийской сетки');
    } finally {
      setDeleteLoading(false);
    }
  };

  const renderMatch = (match: PlayoffMatch) => {
    const isEditing = editingMatchId === match.match_id;
    const isMatchReady = Boolean(match.participant1_id && match.participant2_id);
    const isWaitingForOpponent = !match.played && !isMatchReady;
    const showInputs = isOrganizer && isMatchReady && (!match.played || isEditing);

    const localScores = editScores[match.match_id] || {
      score1: match.score1 !== null && match.score1 !== undefined ? String(match.score1) : '',
      score2: match.score2 !== null && match.score2 !== undefined ? String(match.score2) : '',
    };

    const canSave =
      localScores.score1 !== '' &&
      localScores.score2 !== '' &&
      !isNaN(parseInt(localScores.score1, 10)) &&
      !isNaN(parseInt(localScores.score2, 10));

    const cellClass = styles.matchCell;

    return (
      <div key={match.match_id} className={cellClass}>
        {[match.participant1_id, match.participant2_id].map((pid, idx) => {
          if (!pid) return <div key={idx} className={styles.emptyCell}>—</div>;
          const p = participantMap[pid];
          const score = idx === 0 ? localScores.score1 : localScores.score2;
          const isWinner = match.winner_id === pid && match.played;
          const winnerRadius = isWinner ? (idx === 0 ? '12px 12px 0 0' : '0 0 12px 12px') : undefined;

          return (
            <div
              key={pid}
              className={styles.playerCell}
              style={isWinner ? {
                background: 'linear-gradient(90deg, #eaffea 80%, #f6fff6 100%)',
                boxShadow: '0 2px 8px 0 #38b73822',
                borderRadius: winnerRadius,
                fontWeight: 'bold',
                color: '#38b738',
              } : {}}
            >
              <span
                className={styles.playerName}
                style={isWinner ? { fontWeight: 'bold', color: '#38b738' } : {}}
              >
                {p?.displayName || '—'}
              </span>
              <span className={styles.playerCellBar} />
              {showInputs ? (
                <input
                  type="number"
                  min={0}
                  className={styles.scoreInput}
                  value={score}
                  onChange={e => {
                    const value = e.target.value;
                    setEditScores(prev => {
                      const prevScores = prev[match.match_id] || { score1: '', score2: '' };
                      return {
                        ...prev,
                        [match.match_id]: idx === 0
                          ? { ...prevScores, score1: value }
                          : { ...prevScores, score2: value },
                      };
                    });
                  }}
                />
              ) : (
                <span className={styles.playerScore}>
                  {score !== '' && score !== undefined ? score : ''}
                </span>
              )}
            </div>
          );
        })}

        {isWaitingForOpponent && (
          <div className={styles.matchActions}>
            <span>Ожидает соперника</span>
          </div>
        )}

        {isOrganizer && !isWaitingForOpponent && (
          <div className={styles.matchActions}>
            {isEditing ? (
              <>
                <button
                  className={styles.saveButton}
                  onClick={() => handleSave(match.match_id)}
                  disabled={savingMatchId === match.match_id || !canSave}
                >
                  {savingMatchId === match.match_id ? '...' : 'Сохранить'}
                </button>
                <button
                  className={styles.cancelEditButton}
                  onClick={() => handleCancelEdit(match.match_id)}
                >
                  Отмена
                </button>
              </>
            ) : match.played ? (
              <button
                className={styles.editButton}
                onClick={() => handleStartEdit(match)}
              >
                Изменить счёт
              </button>
            ) : (
              <button
                className={styles.saveButton}
                onClick={() => handleSave(match.match_id)}
                disabled={savingMatchId === match.match_id || !canSave}
              >
                {savingMatchId === match.match_id ? '...' : 'Сохранить'}
              </button>
            )}
          </div>
        )}
      </div>
    );
  };

  if (loading) return <div>Загрузка олимпийской сетки...</div>;
  if (error) return <div style={{ color: 'red' }}>{error}</div>;
  if (!stage || !stage.brackets) return null;
  if (!Array.isArray(stage.brackets) || stage.brackets.length === 0) {
    return (
      <div style={{ textAlign: 'center', margin: '32px 0' }}>
        <div style={{ color: '#888', marginBottom: 12 }}>Олимпийская сетка не создана или пуста.</div>
        {canDelete && (
          <>
            <button
              style={{ background: '#f95e1b', color: '#fff', border: 'none', borderRadius: 6, padding: '6px 16px', fontWeight: 600, cursor: 'pointer' }}
              onClick={handleDeleteGrid}
              disabled={deleteLoading}
            >
              {deleteLoading ? 'Удаление...' : 'Удалить пустую сетку'}
            </button>
            {deleteError && <div style={{ color: 'red', marginTop: 6 }}>{deleteError}</div>}
          </>
        )}
      </div>
    );
  }

  return (
    <div className={styles.playoffStageWrapper}>
      {canDelete && (
        <div style={{ textAlign: 'right', marginBottom: 12 }}>
          <button
            style={{ background: '#f95e1b', color: '#fff', border: 'none', borderRadius: 6, padding: '6px 16px', fontWeight: 600, cursor: 'pointer' }}
            onClick={handleDeleteGrid}
            disabled={deleteLoading}
          >
            {deleteLoading ? 'Удаление...' : 'Удалить олимпийскую сетку'}
          </button>
          {deleteError && <div style={{ color: 'red', marginTop: 6 }}>{deleteError}</div>}
        </div>
      )}
      {stage.brackets.map(bracket => {
        const disablePreliminaryConnectors = isCompressed16Bracket(bracket);

        return (
          <div key={bracket.bracket_id} className={styles.bracketBlock}>
            <h3 className={styles.bracketTitle}>
              {bracket.type === 'main' ? 'Основная сетка' : 'Доп. сетка'}
            </h3>
            <div style={{ overflowX: 'auto', width: '100%' }}>
              <div className={styles.bracketGrid}>
                {bracket.rounds.map((round, roundIdx) => {
                  const isLastRound = roundIdx === bracket.rounds.length - 1;
                  const isPreliminaryRound = disablePreliminaryConnectors && roundIdx === 0;
                  const isAfterPreliminaryRound = disablePreliminaryConnectors && roundIdx === 1;
                  const slotHeight = BASE_SLOT_HEIGHT * Math.pow(2, roundIdx);
                  const sortedMatches = round.matches
                    .slice()
                    .sort((a, b) => (a.order ?? a.match_id) - (b.order ?? b.match_id));
                  const preliminarySlots = isPreliminaryRound
                    ? sortedMatches.reduce<(PlayoffMatch | null)[]>((slots, match, matchIdx) => {
                        const slotIndex = getCompressed16PreliminarySlotIndex(
                          matchIdx,
                          sortedMatches.length,
                        );
                        slots[slotIndex] = match;
                        return slots;
                      }, Array(8).fill(null))
                    : null;
                  const displayMatches = preliminarySlots ?? sortedMatches;

                  return (
                    <div key={round.round_id} className={styles.roundColumn}>
                      <div className={styles.roundName}>{round.name}</div>
                      {displayMatches.map((match, matchIdx) => {
                        const slotClasses = [styles.matchSlot];
                        if (isPreliminaryRound && match) {
                          slotClasses.push(styles.preliminaryRoute);
                        }
                        if (!isLastRound && !isPreliminaryRound) {
                          if (matchIdx % 2 === 0) slotClasses.push(styles.matchSlotFirst);
                          else slotClasses.push(styles.matchSlotLast);
                        }
                        if (roundIdx > 0 && !isAfterPreliminaryRound) {
                          slotClasses.push(styles.matchSlotIncoming);
                        }
                        return (
                          <div
                            key={match?.match_id ?? `empty-${round.round_id}-${matchIdx}`}
                            className={slotClasses.join(' ')}
                            style={{ height: slotHeight }}
                          >
                            {match ? renderMatch(match) : null}
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default PlayoffStage;

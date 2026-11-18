inductive State where
  | notFavorite | saving | favorite | saveFailed
  deriving DecidableEq, Repr

inductive Event where
  | tapFavorite | saveSucceeded | saveFailed | retry | tapFavoriteAgain
  deriving DecidableEq, Repr

def step : State → Event → State
  | .notFavorite, .tapFavorite => .saving
  | .saving, .saveSucceeded => .favorite
  | .saving, .saveFailed => .saveFailed
  | .saveFailed, .retry => .saving
  | .favorite, .tapFavoriteAgain => .notFavorite
  | state, _ => state

/-- Solo se llega a «favorito» desde «guardando»: no hay atajo que evite el guardado. -/
theorem favorite_only_after_saving (state : State) (event : Event) :
    step state event = .favorite → state = .saving ∨ state = .favorite := by
  cases state <;> cases event <;> simp [step]

/-- Un error de guardado nunca deja el producto como favorito. -/
theorem failure_never_marks_favorite (state : State) :
    step state .saveFailed = .favorite → state = .favorite := by
  cases state <;> simp [step]

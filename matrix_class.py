import pickle
from copy import deepcopy, copy
import numpy as np
import scipy.sparse
import nltk
from itertools import permutations

import sowe2bow as s2b

class DS_matrix:

    def __init__(self, matrix_path=None):
        if not matrix_path is None:
            with open(matrix_path, "rb") as matrix_file:
                self.matrix = pickle.load(matrix_file).tocsc()
            prefix = matrix_path[:-11]

            order_path = prefix + "_vector_index.pkl"
            with open(order_path, "rb") as order_file:
                self.vocab_order = pickle.load(order_file)

            unigram_path = prefix + "_unigram_probs.pkl"
            with open(unigram_path, "rb") as unigram_file:
                self.unigram_probs = pickle.load(unigram_file)
        else:
            self.matrix = None
            self.vocab_order = dict()
            self.unigram_probs = dict()


    def get_vector(self, word):
        """
        Return the vector that represents word.
        """
        if not word in self.vocab_order:
            raise Exception("Word not in matrix")

        pos = self.vocab_order[word]
        
        return self.matrix[pos].toarray()

    def contains(self, word):
        """
        Returns true if word is in matrix. False otherwise.
        """
        return word in self.vocab_order
    
    def get_bigram_prob(self, word, prev_word):
        """
        Return the probability p(word|prev_word).
        """

        if not word in self.vocab_order:
            print(word)
            raise Exception("Word not in matrix")

        if not prev_word in self.vocab_order:
            print(prev_word)
            raise Exception("Previous word not in matrix")

        prev_pos = self.vocab_order[prev_word]
        pos = self.vocab_order[word]

        return self.matrix[pos, prev_pos]

    def get_words(self):
        """
        Return words contained in the matrix.
        """

        return list(self.vocab_order.keys())

    def generate_bigram_sentence(self, start_word=("START$_",)):
        """
        Generate a sentence according to the bigram probabilities in the matrix.
        
        Parameter
        ---------
        start_word : tuple(string)
            First word(s) from which to generate sentences.

        Return
        ------
        sentence : [String]
            Generated sentence, without beginning and end symbols.
        """


        
        sentence = []

        if start_word != ("START$_",) and start_word != ("END$_",):
            start_word = map(lambda x:x.lower(), start_word)

        if not start_word in self.vocab_order:
            raise Exception("given start_word not in matrix")

        word = start_word

        words = self.get_words()


        
        while word != "END$_":

            pos = self.vocab_order[word]
            prob_list = self.matrix.getcol(pos).toarray().flatten()

            if sum(prob_list) == 0:
                #deal with possible cases where a word was never seen as first word in bigram using backoff
                #happens when model was trained using stopwords
                prob_list = []
                for next_word in words:
                    prob = self.get_unigram_prob(next_word)
                    prob_list.append(prob)
                
                index = np.random.choice(range(len(words)), p=prob_list)
                word = words[index]
                while word == "START$_":
                    #we don't want to have START$_ in the middle of the sentence
                    index = np.random.choice(range(len(words)), p=prob_list)
                    word = words[index]

            else:
                index = np.random.choice(range(len(words)), p=prob_list)
                word = words[index]

            if word == ("END$_",):
                break
            
            sentence += list(word)
            

        return sentence

    def get_sentence_prob(self, sentence):
        """
        Get the probability of a sentence according to the bigram model.

        Parameter
        ---------
        sentence : [String]
            Sentence of which to get the probability.

        Returns
        -------
        prob : float
            Probability of that sentence.
        """

        prob = 1
        prev_word = ("START$_",)

        sent = list(map(lambda x: x.lower(), sentence))
        while sent != []:
            ngram = (sent[0],)
            for ngram2 in self.vocab_order:
                if len(ngram2) > 1:
                    if sent[:len(ngram2)] == list(ngram2):
                        ngram = ngram2
            sent = sent[len(ngram):]

            if not ngram in self.vocab_order:
                continue

            curr_prob = self.get_bigram_prob(ngram, prev_word)

            while curr_prob == 0 and len(prev_word)>1: #backoff
                prev_word = prev_word[:-1]
                if prev_word in self.vocab_order:
                    curr_prob = self.get_bigram_prob(ngram, prev_word)
                    if curr_prob != 0:
                        break
            
            prob *= curr_prob
            prev_word = ngram
        
        curr_prob = self.get_bigram_prob(("END$_",), prev_word)
        while curr_prob == 0 and len(prev_word)>1: #backoff
                prev_word = prev_word[:-1]
                if prev_word in self.vocab_order:
                    curr_prob = self.get_bigram_prob(("END$_",), prev_word)
                    if curr_prob != 0:
                        break
        prob *= curr_prob#self.get_bigram_prob("END$_", prev_word)

        return prob


    def get_unigram_prob(self, word):
        """
        Get the probability of a specific word ocuuring.

        Parameter
        ---------
        word : string
            Word of which to get the probability.

        Return
        ------
        prob : float
            Probability of word occuring.
        """

        prob = self.unigram_probs[word]

        return prob


    def encode_sentence(self, sent, encode_ngrams=True):
        """
        Encode a sentence as sum of word vectors.
        Unknown words are ignored.

        Parameter
        ---------
        sent : String
            Sentence to be encoded.
        encode_ngrams : Bool
            Whether to use the vectors representing ngrams (n>1) for the encoding,
            or whether to encode each word separately.

        Return
        ------
        encoding : np.ndarray
            Vector representing the words of the sentence.
        """

        words = list(map(lambda x:x.lower(), nltk.word_tokenize(sent)))
        vectors = []

        #for word in words:
        #    if word.lower() in self.vocab_order:
        #        vectors.append(self.get_vector(word.lower()))
        while words != []:
            prefixes = [tuple(words[:i]) for i in range(len(words) + 1)]
            prefixes.reverse()

            for pref in prefixes:
                if pref in self.vocab_order:
                    vectors.append(self.get_vector(pref))
                    words = words[len(pref):]
                    break

        if len(vectors) == 0:
            encoding = np.zeros((1,self.matrix.shape[1]))
        else:
            encoding = np.sum(vectors, axis=0)

        return encoding

    def less_words_matrix(self, word_set, normalize=False):
        """
        Return a DS_matrix whose matrix contains less rows (so as to have a smaller set of words),
        but the same number of columns so that each word retains its original encoding.

        Parameters
        ----------
        word_set : [str]
            Words whose rows are to be retained. 
            Words not contained in the original matrix are ignored.
        normalize : bool
            If true, normalize the bigram probabilities.
            If false, the resulting matrix can't be used as a bigram model.

        Return
        ------
        new_matrix : DS_matrix
            New DS_matrix without the specific rows.
        """

        new_matrix = DS_matrix()

        contained_words = set()
        for word in word_set:
            if word in self.vocab_order:
                contained_words.add(word)
        word_set = contained_words

        word_set.add(("START$_",))
        word_set.add(("END$_",))

        new_matrix.matrix = scipy.sparse.lil_matrix((len(word_set), len(self.vocab_order)))

        for i, word in enumerate(word_set):
            new_matrix.vocab_order[word] = i
            new_matrix.unigram_probs[word] = self.unigram_probs[word]

            pos = self.vocab_order[word]
            new_matrix.matrix[i] = self.matrix.getrow(pos)

        new_matrix.tocsc()

        if normalize:
            #normalize probabilities
            rows, columns = new_matrix.matrix.nonzero()
            entry_dict = dict()
            for row, col in zip(rows, columns):
                if col in entry_dict.keys():
                    entry_dict[col].append(row)
                else:
                    entry_dict[col] = [row]

            for i, col in enumerate(columns):
                if i % 1000 == 0:
                    print(i)
                prob_sum = new_matrix.matrix.getcol(col).sum()

                for row in entry_dict[col]:
                    new_matrix.matrix[row, col] /= prob_sum

        return new_matrix

    def tocsr(self):
        """
        Transform self.matrix to scipy.sparse.csr_matrix.
        This is useful for row slicing, 
        for example when get_vector() is called many times.
        """

        self.matrix = self.matrix.tocsr()

    def tocsc(self):
        """
        Transform self.matrix to scipy.sparse.csc_matrix.
        This is useful for column slicing,
        for example when generate_bigram_sentence is called many times.
        """

        self.matrix = self.matrix.tocsc()

    def todok(self):
        """
        Transform self.matrix to scipy.sparse.dok_matrix.
        This is useful for accessing individual elements,
        for example when get_bigram_prob() is called many times.
        """

        self.matrix = self.matrix.todok()

    def reconstruct_sent(self, sent, beam_width=3):
        """
        Reconstruct a sentence using the DS model
        to reconstruct the bag  of words and the 
        bigram model to reconstruct the word order.

        Parameter
        ---------
        sent : str
            Sentence to be encoded and reconstructed.
        beam_width : int
            Number of words to add for each iteration 
            of the breadth-first search.

        Return
        ------
        best_sent : str
            Reconstructed sentence.
        """

        target = self.encode_sentence(sent)
        
        words, _ = s2b.greedy_search(self, target)

        print("reconstructed bag of words ...")
        
        self.todok()

        #beam search
        start_word_prob = lambda w : self.get_bigram_prob(w, ("START$_",))

        if words == []:
            return ""
        
        first_word = max(words, key=start_word_prob)
        prob = start_word_prob(first_word)

        queue = [([first_word], prob)]
        curr_length = 1
        solutions = []

        while queue != []:
            word_list, prob_thus_far = queue.pop(0)
            words_left = copy(words)
            for w in word_list:
                if w in words_left:
                    words_left.remove(w)

            last_word = word_list[-1]

            if len(word_list) < len(words) - 1:

                expansions = []

                for w in set(words_left):
                    prob = self.get_bigram_prob(w, last_word)

                    expansions.append((w, prob))

                if len(expansions) < beam_width:
                    best_expansions = expansions
                else:
                    expansions.sort(key=(lambda t: t[1]), reverse=True)
                    best_expansions = expansions[:beam_width]

                for w, p in best_expansions:
                    new_word_list = word_list + [w]
                    new_prob = prob_thus_far * p
                    queue.append((new_word_list, new_prob))

                    len_queue = len(queue)
                    if len_queue > 10000:
                        #prune the queue to avoid memory problems
                        #remove one of the first 1000 elements
                        #in order to not accidentally remove all long sequences
                        remove_el = min(queue[:1000], key=(lambda t: t[1]))
                        queue.remove(remove_el)
            else:
                #found full sentence
                w = words_left[0]

                new_prob = (prob_thus_far
                            * self.get_bigram_prob(w, last_word)
                            * self.get_bigram_prob(("END$_",), w))
                sent = word_list + [w]

                solutions.append((sent, new_prob))
                    

        best_order, _ = max(solutions, key=(lambda t: t[1]))
        best_sent = []
        for t in best_order:
            best_sent += t
        best_sent = ' '.join(best_sent)


        return best_sent
        



